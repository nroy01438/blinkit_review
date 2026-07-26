"""Single source of truth for environment/config. Fails loudly (never
silently falls back) when a value required for the operation being
attempted is missing — see `require()`.
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../aisle
CONFIG_DIR = REPO_ROOT / "config"
TAXONOMY_DIR = REPO_ROOT / "taxonomy"
PROMPTS_DIR = REPO_ROOT / "prompts"
DATA_DIR = REPO_ROOT / "data"


class MissingConfigError(RuntimeError):
    """Raised instead of silently defaulting when a required key is absent."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), extra="ignore")

    mock_mode: bool = True
    mock_llm: bool = True

    database_url: str = "postgresql://aisle:aisle@localhost:5433/aisle_dev"

    anthropic_api_key: str | None = None
    aisle_bulk_model: str = "claude-sonnet-5"
    aisle_synth_model: str = "claude-opus-5"
    aisle_max_cost_usd: float = 25.0

    embedding_model: str = "sentence-transformers/all-MiniLM-L12-v2"

    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "aisle-discovery-engine/0.1"

    author_hash_salt: str = "change-me-in-prod"
    cron_secret: str = "change-me-in-prod"
    aisle_api_port: int = 8000

    def require(self, field: str) -> str:
        value = getattr(self, field, None)
        if not value:
            raise MissingConfigError(
                f"'{field}' is required for this operation but is not set. "
                f"Set it in .env, or set MOCK_MODE=true/MOCK_LLM=true to run without it."
            )
        return value


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


@functools.lru_cache
def load_yaml_config(name: str) -> dict:
    """Load a YAML file from config/ by filename, e.g. 'scoring.yaml'."""
    path = CONFIG_DIR / name
    if not path.exists():
        raise MissingConfigError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


@functools.lru_cache
def load_taxonomy(name: str) -> dict:
    path = TAXONOMY_DIR / name
    if not path.exists():
        raise MissingConfigError(f"Taxonomy file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def scoring_config() -> dict:
    return load_yaml_config("scoring.yaml")


def sources_config() -> dict:
    return load_yaml_config("sources.yaml")


def question_packs_config() -> dict:
    return load_yaml_config("question_packs.yaml")


def codes_taxonomy() -> dict:
    return load_taxonomy("codes.yaml")


def themes_taxonomy() -> dict:
    return load_taxonomy("themes.yaml")
