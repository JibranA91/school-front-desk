"""Bedrock chat model factory (Claude via langchain-aws). Lazy — only imported
and constructed on the real path, when AWS creds are present. Cached per model id
so the parent (Haiku) and operator (Sonnet) models can coexist."""

from __future__ import annotations

from app.config import settings

_cache: dict[str, object] = {}


def get_chat_model(
    model_id: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
):
    mid = model_id or settings.bedrock_chat_model
    key = f"{mid}#{max_tokens}#{temperature}"  # cache per (model, budget, temp)
    if key not in _cache:
        import boto3
        from langchain_aws import ChatBedrockConverse

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        kwargs: dict = {"client": client, "model": mid, "max_tokens": max_tokens}
        if temperature is not None:
            kwargs["temperature"] = temperature
        _cache[key] = ChatBedrockConverse(**kwargs)
    return _cache[key]
