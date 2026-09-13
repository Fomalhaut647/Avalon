"""对 DeepSeek 的 OpenAI 兼容接口的封装。不含任何游戏逻辑。

职责：发送 messages、超时与网络重试、返回文本与 token 用量。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str, timeout_s: float = 120.0) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def complete(self, messages: list[dict[str, str]]) -> LLMResult:
        raise NotImplementedError
