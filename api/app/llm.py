"""Chat-model factory. Returns a LangChain chat model for the configured provider
— Claude via Bedrock (langchain-aws) or the Claude API (langchain-anthropic) —
behind one interface so the agent, structured output, and tool-calling code are
provider-agnostic. Call sites pass a LOGICAL model id (see app.model_catalog),
resolved here to the provider's concrete string. Lazy + cached per (provider,
model, budget, temp)."""

from __future__ import annotations

from app.config import settings
from app.model_catalog import resolve_chat_model

_cache: dict[str, object] = {}


def get_chat_model(
    model_id: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
):
    provider = settings.provider
    # `model_id` is a LOGICAL id (e.g. "sonnet-4.5"); the catalog maps it to the
    # provider's concrete model string (default + log for an unknown id). When
    # omitted, fall back to the configured chat model.
    mid = resolve_chat_model(model_id or settings.chat_model, provider)
    key = f"{provider}#{mid}#{max_tokens}#{temperature}"
    if key not in _cache:
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            kwargs: dict = {
                "model": mid,
                "max_tokens": max_tokens,
                "api_key": settings.anthropic_api_key,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            _cache[key] = ChatAnthropic(**kwargs)
        else:
            import boto3
            from langchain_aws import ChatBedrockConverse

            client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            kwargs = {"client": client, "model": mid, "max_tokens": max_tokens}
            if temperature is not None:
                kwargs["temperature"] = temperature
            _cache[key] = ChatBedrockConverse(**kwargs)
    return _cache[key]
