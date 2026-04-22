from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='NET_AGENT_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    ollama_model: str = 'llama3.2'
    inventory_source: str = 'mock'
    require_approval_for_execute: bool = True
    runs_dir: Path = Path('runs')
    netbox_url: str | None = None
    netbox_token: SecretStr | None = None
    netbox_timeout_seconds: int = 10
    netbox_verify_tls: bool = True


settings = Settings()
