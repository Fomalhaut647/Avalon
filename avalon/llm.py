"""对 DeepSeek 的 OpenAI 兼容接口的封装。不含任何游戏逻辑。

职责：发送 messages、超时与网络重试、返回文本与 token 用量。

重试分两层：SDK 自带的快速重试（秒级退避，应对抖动），以及本模块的慢速重试
（数十秒退避，应对短暂断网或限流），两层都用尽才向上抛出，让一局中断。
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

SLOW_RETRY_DELAYS_S: tuple[float, ...] = (10.0, 30.0, 60.0)
"""慢速重试的等待秒数，共重试 3 次。"""


@dataclass(frozen=True)
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    reasoning: str | None = None
    """开启隐藏思考时接口返回的推理原文。不进玩家线程，只记裁判日志。"""


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

    def _sdk(self):
        # 延迟创建，避免测试环境无 key 时失败。
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_s,
                max_retries=self.max_retries,
            )
        return self._client

    def complete(self, messages: list[dict[str, str]]) -> LLMResult:
        """一次非流式对话补全。网络错误与 429/5xx 先由 SDK 快速重试，再由本方法慢速重试。"""
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
            if delay is None:
                raise err
            print(f"[llm] {self.model} 请求失败（第 {i + 1} 次）：{err}，{delay:.0f} 秒后重试", file=sys.stderr)
            time.sleep(delay)
        latency = time.monotonic() - t0
        message = resp.choices[0].message if resp.choices else None
        text = (message.content or "") if message else ""
        reasoning = getattr(message, "reasoning_content", None) if message else None
        usage = resp.usage
        return LLMResult(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_s=latency,
            reasoning=reasoning or None,
        )
