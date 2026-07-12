"""Bedrock chat model factory (Claude via langchain-aws). Lazy — only imported
and constructed on the real path, when AWS creds are present."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=1)
def get_chat_model():
    import boto3
    from langchain_aws import ChatBedrockConverse

    client = boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    # Sonnet on Bedrock (Converse API). Model id is env-overridable to whatever
    # inference profile is enabled in the account (Sonnet or Haiku only).
    return ChatBedrockConverse(client=client, model=settings.bedrock_chat_model, max_tokens=1024)
