from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@lru_cache(maxsize=1)
def _default_creds_available() -> bool:
    """True if boto3 can resolve credentials from the standard chain
    (env vars, ~/.aws/credentials, SSO, instance role, …). Checked once."""
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:  # noqa: BLE001
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database. Managed Postgres providers (Railway, Heroku, …) hand out a URL
    # like `postgres://…` or `postgresql://…`; the validator below rewrites it to
    # the `postgresql+psycopg://` driver form SQLAlchemy needs here.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/frontdesk"

    # Optional first-boot seeding for hosted deploys (e.g. Railway): "" = off
    # (default), "demo" = full demo, "fresh" = scaffold only (empty KG + inbox).
    # Runs ONLY when the database has no users yet, so it never wipes live data.
    seed_on_start: str = ""

    # Auth — shared secret the `web` service uses to authenticate to this API.
    auth_shared_secret: str = "dev-shared-secret-change-me"

    # Which chat backend to use: "bedrock" | "anthropic" | "mock" | "auto".
    # auto = Bedrock if AWS creds resolve, else Anthropic if a key is set, else mock.
    # Set LLM_PROVIDER=anthropic to use the Claude API even where AWS creds exist.
    llm_provider: str = "auto"

    # AWS Bedrock. Creds resolve via the standard boto3 chain (env or ~/.aws).
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # Legacy explicit override: USE_BEDROCK=true/false. Prefer LLM_PROVIDER now.
    use_bedrock: bool | None = None

    # Anthropic Claude API (used when provider == "anthropic").
    anthropic_api_key: str | None = None

    # Model ids (Bedrock inference profiles; env-overridable to enabled models).
    # Parent chat → Haiku (fast, cheap). Operator agents (author/cleanup) → Sonnet.
    bedrock_parent_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_chat_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    # Anthropic-API model ids (plain, no inference-profile prefix/suffix).
    anthropic_parent_model: str = "claude-haiku-4-5"
    anthropic_chat_model: str = "claude-sonnet-4-5"
    embedding_dims: int = 1024

    # Which embedder to use: "voyage" | "titan" | "mock" | "auto" (default).
    # auto = Voyage if VOYAGE_API_KEY is set, else Titan in bedrock mode, else the
    # offline mock. Voyage is independent of the CHAT provider, so it gives the
    # Anthropic/Claude path (which has no first-party embeddings API) real
    # semantic vectors instead of the mock.
    embeddings_provider: str = "auto"
    # Voyage AI (the `voyageai` package). Its models default to 1024 dims, which
    # matches embedding_dims and the pgvector column — so switching is a
    # dimension drop-in (no schema change). voyage-4* carry a 200M-token free tier.
    voyage_api_key: str | None = None
    voyage_embedding_model: str = "voyage-3.5"

    # CORS — the web origin allowed to call this API.
    web_origin: str = "http://localhost:3000"

    # Which retrieval backend the agent reads through. Swap this to point the
    # knowledge base at a different store behind the same Retriever interface.
    retriever: str = "pgvector"

    # Semantic (vector) retrieval. Set EMBEDDINGS_ENABLED=false to turn off the
    # pgvector signal entirely and rank on Postgres full-text search alone —
    # useful when embeddings are unavailable/untrusted (e.g. the Anthropic path's
    # mock embedder), or to run leaner with no embedding provider at all.
    embeddings_enabled: bool = True

    # Short-term chat memory: how many prior turns of the current session to feed
    # the parent agent so it can resolve follow-ups ("what about fever?"). 0 = off
    # (stateless single-turn). A turn = one user + one assistant message.
    chat_memory_turns: int = 10

    # The relevant subgraph is always pre-retrieved and injected into the parent
    # agent's context. When True, the agent ALSO gets knowledge-graph tools
    # (search_graph/get_entity/expand_neighbors) to look further; when False it
    # relies solely on the injected subgraph (live-data tools are unaffected).
    kg_tools_enabled: bool = True

    # Shape of the auto-injected subgraph (retrieve_subgraph):
    retrieval_k: int = 5              # seed hits from hybrid search
    retrieval_expand_top: int = 3     # how many top hits to expand from
    retrieval_hops: int = 1           # relationship hops to walk
    retrieval_max_entities: int = 25  # safety cap on total injected entities

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Accept the `postgres://` / `postgresql://` URLs managed providers give
        and rewrite them to the `postgresql+psycopg://` driver form. No-op for a
        URL that already names a driver (e.g. `postgresql+psycopg://`)."""
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def provider(self) -> str:
        """Resolved chat backend: 'bedrock', 'anthropic', or 'mock'."""
        p = (self.llm_provider or "auto").lower()
        if p in ("bedrock", "anthropic", "mock"):
            return p
        # Legacy USE_BEDROCK switch still honored when LLM_PROVIDER is unset/auto.
        if self.use_bedrock is True:
            return "bedrock"
        if self.use_bedrock is False:
            return "anthropic" if self.anthropic_api_key else "mock"
        # Auto-detect: prefer an already-configured Bedrock (keeps existing
        # installs unchanged), else Anthropic if a key is set, else mock.
        if (self.aws_access_key_id and self.aws_secret_access_key) or _default_creds_available():
            return "bedrock"
        if self.anthropic_api_key:
            return "anthropic"
        return "mock"

    @property
    def llm_enabled(self) -> bool:
        """True when a real chat model is available (Bedrock or Anthropic)."""
        return self.provider in ("bedrock", "anthropic")

    @property
    def bedrock_enabled(self) -> bool:
        """Whether the resolved CHAT provider is Bedrock. (Embeddings are chosen
        separately — see `embedder`.)"""
        return self.provider == "bedrock"

    @property
    def embedder(self) -> str:
        """Resolved embedding backend: 'voyage', 'titan', or 'mock'.
        auto = Voyage if a key is set, else Titan when chatting on Bedrock, else
        the offline mock. Voyage decouples embeddings from the chat provider, so
        the Anthropic path can have real vectors."""
        e = (self.embeddings_provider or "auto").lower()
        if e in ("voyage", "titan", "mock"):
            return e
        if self.voyage_api_key:
            return "voyage"
        if self.provider == "bedrock":
            return "titan"
        return "mock"


settings = Settings()
