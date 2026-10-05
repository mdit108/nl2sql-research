"""Check that the configured LLM (and optionally an OpenAI-compatible embeddings endpoint) respond.

    python scripts/check_providers.py              # LLM from .env
    python scripts/check_providers.py --embeddings # also try POST /embeddings on the LLM endpoint

Prints model, latency and token usage. Never prints the API key.
"""

import argparse

from app.config import get_settings
from app.llm import get_llm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", action="store_true")
    parser.add_argument("--embedding-model", default=None, help="model name to try on the LLM endpoint")
    args = parser.parse_args()

    s = get_settings()
    print(f"LLM provider={s.llm_provider} base_url={s.llm_base_url} model={s.llm_model}")
    resp = get_llm(s).generate("Reply with exactly: SELECT 1")
    print(f"  ok: {resp.text.strip()[:60]!r} ({resp.latency_ms:.0f} ms, in={resp.input_tokens} out={resp.output_tokens} reasoning={resp.reasoning_tokens})")

    if args.embeddings:
        from openai import OpenAI

        model = args.embedding_model or s.embedding_model
        client = OpenAI(base_url=s.embedding_base_url or s.llm_base_url,
                        api_key=(s.embedding_api_key or s.llm_api_key).get_secret_value())
        try:
            vec = client.embeddings.create(model=model, input=["hello"]).data[0].embedding
            print(f"  embeddings ok: {model} -> {len(vec)} dims")
        except Exception as e:  # noqa: BLE001
            print(f"  embeddings NOT available for {model}: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    main()
