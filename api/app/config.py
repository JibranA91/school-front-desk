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

    # AWS Bedrock. Creds resolve via the standard boto3 chain (env or ~/.aws).
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # Explicit override: set USE_BEDROCK=true/false to force on/off; None = auto-detect.
    use_bedrock: bool | None = None

    # Model ids (Bedrock inference profiles; env-overridable to enabled models).
    # Parent chat → Haiku (fast, cheap). Operator agents (author/cleanup) → Sonnet.
    bedrock_parent_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_chat_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    embedding_dims: int = 1024

    # CORS — the web origin allowed to call this API.
    web_origin: str = "http://localhost:3000"

    @property
    def bedrock_enabled(self) -> bool:
        if self.use_bedrock is not None:
            return self.use_bedrock
        if self.aws_access_key_id and self.aws_secret_access_key:
            return True
        return _default_creds_available()


settings = Settings()
