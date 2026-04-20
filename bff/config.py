"""BFF application settings loaded from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    keycloak_realm_url: str = ""
    keycloak_jwks_uri: str = ""

    gitlab_url: str = ""
    gitlab_token: str = ""

    puppetdb_url: str = ""
    puppetdb_token: str = ""

    puppet_server_url: str = ""
    puppet_server_token: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
