"""Chat-model factory. Returns a LangChain chat model for the configured provider
— Claude via Bedrock (langchain-aws) or the Claude API (langchain-anthropic) —
behind one interface so the agent, structured output, and tool-calling code are
provider-agnostic. Lazy + cached per (provider, model, budget, temp)."""

from __future__ import annotations

from app.config import settings

_cache: dict[str, object] = {}


def _anthropic_model(model_id: str | None) -> str:
    """Map a Bedrock inference-profile id (what call sites pass) to the equivalent
    Anthropic-API model id, so callers don't need to know the active provider."""
    if model_id is None:
        return settings.anthropic_chat_model
    return {
        settings.bedrock_parent_model: settings.anthropic_parent_model,
        settings.bedrock_chat_model: settings.anthropic_chat_model,
    }.get(model_id, model_id)


def get_chat_model(
    model_id: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
):
    provider = settings.provider
    if provider == "anthropic":
        mid = _anthropic_model(model_id)
    else:
        mid = model_id or settings.bedrock_chat_model
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
