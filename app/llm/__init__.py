"""LLM providers. Everything else depends only on `LLMProvider`."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import Settings, get_settings


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None   # includes reasoning tokens, if any
    reasoning_tokens: int | None = None
    latency_ms: float = 0.0


class LLMProvider(ABC):
    model: str

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> LLMResponse: ...


class OpenAICompatibleProvider(LLMProvider):
    """Any endpoint that speaks POST /chat/completions (hosted APIs, vLLM, Ollama, ...)."""

    def __init__(self, settings: Settings):
        from openai import OpenAI

        if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value():
            raise RuntimeError("LLM_API_KEY is not set (see .env.example), or use LLM_PROVIDER=mock")
        # Retries with backoff on rate limits / transient errors, so one hiccup doesn't kill a long run.
        self.client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key.get_secret_value(),
                             max_retries=5)
        self.model = settings.llm_model
        # None = the model rejected the parameter and runs at its own default (recorded in the manifest).
        self.temperature: float | None = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    def _create(self, messages: list[dict]):
        from openai import BadRequestError

        # max_completion_tokens is the current OpenAI parameter; reasoning models reject max_tokens.
        kwargs = {"model": self.model, "messages": messages, "max_completion_tokens": self.max_tokens}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            return self.client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            if "temperature" in str(e) and "temperature" in kwargs:
                self.temperature = None  # later calls skip it; concurrent calls retry the same way
                kwargs.pop("temperature")
                return self.client.chat.completions.create(**kwargs)
            raise

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}]
        start = time.perf_counter()
        resp = self._create(messages)
        latency = (time.perf_counter() - start) * 1000
        usage = resp.usage
        details = getattr(usage, "completion_tokens_details", None) if usage else None
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            model=resp.model or self.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            reasoning_tokens=getattr(details, "reasoning_tokens", None),
            latency_ms=latency,
        )


class MockProvider(LLMProvider):
    """Deterministic provider for tests: returns canned SQL chosen by a substring of the prompt."""

    model = "mock"

    def __init__(self, responses: dict[str, str] | None = None, default: str = "SELECT 1"):
        self.responses = responses or {}
        self.default = default
        self.prompts: list[str] = []

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        self.prompts.append(prompt)
        # Match on the question section only, so context text can't trigger a canned answer.
        question = prompt.rsplit("Question:", 1)[-1]
        text = next((sql for key, sql in self.responses.items() if key in question), self.default)
        return LLMResponse(text=f"```sql\n{text}\n```", model=self.model,
                           input_tokens=len(prompt) // 4, output_tokens=len(text) // 4)


def get_llm(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(settings)
    raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}")
