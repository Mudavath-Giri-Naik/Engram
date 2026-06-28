from __future__ import annotations
from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env.local",), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)
    app_env: Literal["dev","staging","prod"]="dev"
    api_host: str="0.0.0.0"
    api_port: int=8000
    database_url: str=Field(default="sqlite+pysqlite:///./engram.db")
    qdrant_url: str=":memory:"
    qdrant_api_key: str|None=None
    qdrant_collection: str="engram_incidents"
    embedding_model: str="hashing"
    embedding_dim: int=384
    llm_provider: str=""
    llm_model: str=""
    llm_api_key: str=""
    engram_bootstrap_api_key: str="local-dev-key"
    engram_bootstrap_network_id: str="acme-core-network"
    device_ssh_username: str=""
    device_ssh_password: str=""
    devnet_host: str="x"
    devnet_user: str="x"
    devnet_password: str="x"
    devnet_port: int=22
    devnet_device_type: str="cisco_xe"
    retrieval_w_vector: float=0.6
    retrieval_w_structured: float=0.4
    staleness_age_days: int=180
    @property
    def llm_configured(self)->bool:
        k=self.llm_api_key.strip().upper(); return bool(self.llm_provider and self.llm_model and k and not k.startswith(("REPLACE","PASTE")) and "YOUR_" not in k)
@lru_cache(maxsize=1)
def get_settings()->Settings: return Settings()
