from functools import lru_cache

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

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/frontdesk"

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
        """Whether embeddings are served by Bedrock Titan. Only in bedrock mode —
        the anthropic and mock paths use the offline mock embedder (Anthropic has
        no embeddings API)."""
        return self.provider == "bedrock"


settings = Settings()
