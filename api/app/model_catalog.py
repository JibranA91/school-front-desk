"""Logical chat-model catalog.

Config sets a provider (LLM_PROVIDER) and a *logical* model id — e.g.
`sonnet-4.5`, `haiku-4.5` (also written `Sonnet45`, `haiku4.5`, … — matching is
case/punctuation-insensitive). This catalog maps that logical id to the concrete
model string each provider expects, so call sites never hard-code a Bedrock
inference-profile or an Anthropic model name.

Unknown id for the active provider -> the provider's default model, logged once
(so a typo or a not-yet-catalogued model still runs, visibly).

Add a model = one entry in ChatModelCatalog.MODELS. (Embeddings are a separate
axis — see settings.embedder / embeddings.py — and are intentionally not here.)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("app.model_catalog")


def _norm(s: str) -> str:
    """Fold a logical id to a comparison key: lowercase, alphanumerics only.
    So 'Sonnet4.5', 'sonnet-4.5', 'SONNET_45' all collapse to 'sonnet45'."""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


class ChatModelCatalog:
    # logical id -> { provider: concrete model string }
    MODELS: dict[str, dict[str, str]] = {
        "haiku-4.5": {
            "bedrock": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "anthropic": "claude-haiku-4-5",
        },
        "sonnet-4.5": {
            "bedrock": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "anthropic": "claude-sonnet-4-5",
        },
    }

    # Fallback per provider when a logical id isn't catalogued for it.
    PROVIDER_DEFAULT: dict[str, str] = {
        "bedrock": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "anthropic": "claude-sonnet-4-5",
    }

    # normalized logical id -> entry (built once from MODELS)
    _BY_NORM: dict[str, dict[str, str]] = {}
    _warned: set[tuple[str, str]] = set()

    @classmethod
    def _index(cls) -> dict[str, dict[str, str]]:
        if not cls._BY_NORM:
            cls._BY_NORM = {_norm(k): v for k, v in cls.MODELS.items()}
        return cls._BY_NORM

    @classmethod
    def resolve(cls, logical_id: str | None, provider: str) -> str:
        """Concrete model string for (logical_id, provider). Falls back to the
        provider default (logged once) when there's no catalog entry."""
        entry = cls._index().get(_norm(logical_id))
        if entry and provider in entry:
            return entry[provider]
        default = cls.PROVIDER_DEFAULT.get(provider, logical_id or "")
        key = (_norm(logical_id), provider)
        if key not in cls._warned:
            cls._warned.add(key)
            logger.warning(
                "model_catalog: no mapping for model %r on provider %r; "
                "using provider default %r. Known ids: %s",
                logical_id, provider, default, sorted(cls.MODELS),
            )
        return default


def resolve_chat_model(logical_id: str | None, provider: str) -> str:
    return ChatModelCatalog.resolve(logical_id, provider)
