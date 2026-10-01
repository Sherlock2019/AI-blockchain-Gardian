"""Runtime configuration, read once from the environment."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = REPO_ROOT / "data"
    database_url: str = f"sqlite:///{REPO_ROOT / 'backend' / 'trustchain.db'}"

    # "memory" simulates the registry in-process; "hardhat" talks to a JSON-RPC node.
    ledger_mode: str = "memory"
    ledger_rpc_url: str = "http://127.0.0.1:8545"
    ledger_deployment_file: Path = REPO_ROOT / "blockchain" / "deployments" / "localhost.json"

    llm_provider: str = "mock"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # The mock model can be told to follow injected instructions, so the demo
    # shows governance holding when the model does not.
    mock_llm_obeys_injection: bool = True

    # Ephemeral unless configured: approvals signed before a restart then fail
    # verification, which is the safe direction.
    approval_signing_secret: str = field(default_factory=lambda: secrets.token_hex(32))

    demo_mode: bool = True
    rate_limit_per_minute: int = 120
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        defaults = cls()
        return cls(
            data_dir=Path(env.get("DATA_DIR", defaults.data_dir)),
            database_url=env.get("DATABASE_URL", defaults.database_url),
            ledger_mode=env.get("LEDGER_MODE", defaults.ledger_mode).lower(),
            ledger_rpc_url=env.get("LEDGER_RPC_URL", defaults.ledger_rpc_url),
            ledger_deployment_file=Path(
                env.get("LEDGER_DEPLOYMENT_FILE", defaults.ledger_deployment_file)
            ),
            llm_provider=env.get("LLM_PROVIDER", defaults.llm_provider).lower(),
            openai_base_url=env.get("OPENAI_BASE_URL", defaults.openai_base_url),
            openai_api_key=env.get("OPENAI_API_KEY", ""),
            openai_model=env.get("OPENAI_MODEL", defaults.openai_model),
            mock_llm_obeys_injection=_bool("MOCK_LLM_OBEYS_INJECTION", True),
            approval_signing_secret=env.get("APPROVAL_SIGNING_SECRET")
            or defaults.approval_signing_secret,
            demo_mode=_bool("DEMO_MODE", True),
            rate_limit_per_minute=int(env.get("RATE_LIMIT_PER_MINUTE", "120")),
            cors_origins=tuple(
                o.strip()
                for o in env.get("CORS_ORIGINS", ",".join(defaults.cors_origins)).split(",")
                if o.strip()
            ),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
        )
