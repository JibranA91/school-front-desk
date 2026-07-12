from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/frontdesk"

    # Auth — shared secret the `web` service uses to authenticate to this API.
    auth_shared_secret: str = "dev-shared-secret-change-me"

    # AWS Bedrock (optional until the agents are wired; mock fallback used if absent)
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # Model ids — confirmed against the claude-api skill at integration time.
    bedrock_chat_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    embedding_dims: int = 1024

    # CORS — the web origin allowed to call this API.
    web_origin: str = "http://localhost:3000"

    @property
    def bedrock_enabled(self) -> bool:
        return bool(self.aws_access_key_id and self.aws_secret_access_key)


settings = Settings()
