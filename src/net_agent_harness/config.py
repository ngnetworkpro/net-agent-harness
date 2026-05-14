from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='NET_AGENT_',
        env_file=str(Path(__file__).parent.parent.parent / '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
    )
    
    # config.py additions
    provider: str | None = None           # e.g. "nvidia", "ollama", "openai"
    openai_model: str = "gpt-4o-mini"     # used only if provider="openai"
    ollama_model: str = 'qwen3.5:9b'
    nvidia_api_key: str | None = None
    nvidia_model: str = 'minimaxai/minimax-m2.7' # optional 'mistralai/mistral-nemotron'
    inventory_source: str = 'mock'
    execution_backend: str = "direct_api"
    terraform_render_source: str = "auto"  # auto | local | github
    terraform_source_dir: str = "src/library/terraform"
    terraform_source_networks_file: str = "mist_networks.json"
    terraform_source_template_file: str = "mist.tf"
    terraform_networks_file: str | None = None
    github_repo: str | None = None
    github_token: SecretStr | None = None
    github_base_branch: str = "main"
    require_approval_for_execute: bool = True
    runs_dir: Path = Path('runs')
    netbox_url: str | None = None
    netbox_token: SecretStr | None = None
    netbox_timeout_seconds: int = 10
    netbox_verify_tls: bool = True


settings = Settings()
