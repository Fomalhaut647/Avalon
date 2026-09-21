"""对 DeepSeek 的 OpenAI 兼容接口的封装。不含任何游戏逻辑。

职责：发送 messages、超时与网络重试、返回文本与 token 用量、按需掐断进行中的请求。

重试分两层：SDK 自带的快速重试（秒级退避，应对抖动），以及本模块的慢速重试
（数十秒退避，应对短暂断网或限流），两层都用尽才向上抛出，让一局中断。

掐断：调用方传入一个 threading.Event，置位后 complete() 立刻抛出 CallCancelled，
并关闭底层 HTTP 客户端以断开连接；仍在后台线程里的那次请求随之失败并被丢弃。
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

from avalon.control import CallCancelled

SLOW_RETRY_DELAYS_S: tuple[float, ...] = (10.0, 30.0, 60.0)
"""慢速重试的等待秒数，共重试 3 次。"""

CANCEL_POLL_S = 0.2
"""等待请求返回时检查掐断信号的间隔。"""


@dataclass(frozen=True)
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    reasoning: str | None = None
    """开启隐藏思考时接口返回的推理原文。不进玩家线程，只记裁判日志。"""
    reasoning_tokens: int = 0
    """输出 token 中属于隐藏推理的部分，已包含在 completion_tokens 内。"""
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    """输入 token 中命中/未命中前缀缓存的部分，两者之和等于 prompt_tokens。"""
    finish_reason: str | None = None
    usage_raw: dict | None = None
    """接口返回的 usage 原样（去掉空值），以防日后字段变化。"""


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: float = 120.0,
        max_retries: int = 3,
        thinking: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.thinking = thinking
        """是否让模型在回复前做隐藏思考。DeepSeek 默认开启，这里默认关闭，见 docs/decisions/0006。"""
        self._client = None
        self._client_lock = threading.Lock()

    def _sdk(self):
        # 延迟创建，避免测试环境无 key 时失败。
        with self._client_lock:
            if self._client is None:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout_s,
                    max_retries=self.max_retries,
                )
            return self._client

    def abort(self) -> None:
        """断开底层 HTTP 连接，让进行中的请求失败；下次调用时重建客户端。"""
        with self._client_lock:
            client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def complete(self, messages: list[dict[str, str]], *, cancel: threading.Event | None = None) -> LLMResult:
        """一次非流式对话补全。cancel 置位时立刻抛出 CallCancelled，请求本身在后台线程里被断开。"""
        if cancel is None:
            return self._complete(messages, None)
        box: dict[str, object] = {}
        done = threading.Event()

        def worker() -> None:
            try:
                box["result"] = self._complete(messages, cancel)
            except BaseException as e:  # noqa: BLE001 - 原样转交主线程
                box["error"] = e
            finally:
                done.set()

        threading.Thread(target=worker, name=f"llm-{self.model}", daemon=True).start()
        while not done.wait(CANCEL_POLL_S):
            if cancel.is_set():
                self.abort()
                raise CallCancelled()
        if cancel.is_set():
            raise CallCancelled()
        if "error" in box:
            raise box["error"]  # type: ignore[misc]
        return box["result"]  # type: ignore[return-value]

    def _complete(self, messages: list[dict[str, str]], cancel: threading.Event | None) -> LLMResult:
        """网络错误与 429/5xx 先由 SDK 快速重试，再由本方法慢速重试。"""
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        extra_body = {"thinking": {"type": "enabled" if self.thinking else "disabled"}}
        t0 = time.monotonic()
        for i, delay in enumerate((*SLOW_RETRY_DELAYS_S, None)):
            try:
                resp = self._sdk().chat.completions.create(
                    model=self.model, messages=messages, extra_body=extra_body
                )
                break
            except (APIConnectionError, APITimeoutError) as e:
                err: Exception = e
            except APIStatusError as e:
                if e.status_code not in (408, 409, 429) and e.status_code < 500:
                    raise
                err = e
            except Exception as e:  # 客户端被 abort() 关闭时 SDK 抛的是普通异常
                if cancel is not None and cancel.is_set():
                    raise CallCancelled() from e
                raise
            if cancel is not None and cancel.is_set():
                raise CallCancelled() from err
            if delay is None:
                raise err
            print(f"[llm] {self.model} 请求失败（第 {i + 1} 次）：{err}，{delay:.0f} 秒后重试", file=sys.stderr)
            if cancel is not None:
                if cancel.wait(delay):
                    raise CallCancelled()
            else:
                time.sleep(delay)
        latency = time.monotonic() - t0
        choice = resp.choices[0] if resp.choices else None
        message = choice.message if choice else None
        text = (message.content or "") if message else ""
        reasoning = getattr(message, "reasoning_content", None) if message else None
        usage = resp.usage.model_dump(exclude_none=True) if resp.usage else {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        hit = int(usage.get("prompt_cache_hit_tokens", usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)))
        miss = int(usage.get("prompt_cache_miss_tokens", prompt_tokens - hit))
        return LLMResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_s=latency,
            reasoning=reasoning or None,
            reasoning_tokens=int(usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)),
            cache_hit_tokens=hit,
            cache_miss_tokens=miss,
            finish_reason=choice.finish_reason if choice else None,
            usage_raw=usage or None,
        )
