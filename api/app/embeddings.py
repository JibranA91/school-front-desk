"""Embedding provider: Bedrock Titan when AWS creds are present, otherwise a
deterministic hashed bag-of-words mock so the whole retrieval pipeline runs
(and is testable) offline. Mock vectors put shared words in shared dimensions,
so cosine similarity still tracks word overlap — good enough to exercise ranking.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from app.config import settings


def tokens(text: str) -> list[str]:
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return [t for t in cleaned.split() if len(t) > 1]


def entity_text(entity) -> str:
    """Serialize an entity into the text we embed."""
    parts: list[str] = [str(entity.type), str(entity.name)]
    for key, val in (entity.attributes or {}).items():
        if isinstance(val, (str, int, float)):
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


def _mock_embed(text: str) -> list[float]:
    dims = settings.embedding_dims
    vec = [0.0] * dims
    for tok in tokens(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@lru_cache(maxsize=1)
def _bedrock():
    import boto3
    from langchain_aws import BedrockEmbeddings

    client = boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return BedrockEmbeddings(client=client, model_id=settings.bedrock_embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.bedrock_enabled:
        return _bedrock().embed_documents(list(texts))
    return [_mock_embed(t) for t in texts]


def embed_query(text: str) -> list[float]:
    if settings.bedrock_enabled:
        return _bedrock().embed_query(text)
    return _mock_embed(text)
