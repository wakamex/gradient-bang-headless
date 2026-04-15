from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DEFAULT_FUNCTIONS_URL = "https://api.gradient-bang.com/functions/v1"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_functions_url(raw: str | None) -> str:
    value = (raw or DEFAULT_FUNCTIONS_URL).strip().rstrip("/")
    if not value:
        return DEFAULT_FUNCTIONS_URL
    return value


def supabase_root_from_functions_url(functions_url: str) -> str:
    normalized = normalize_functions_url(functions_url)
    parsed = urlsplit(normalized)
    path = parsed.path.rstrip("/")
    suffix = "/functions/v1"
    if path.endswith(suffix):
        path = path[: -len(suffix)] or ""
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


@dataclass(slots=True)
class HeadlessConfig:
    functions_url: str
    api_token: str | None = None
    access_token: str | None = None
    character_id: str | None = None
    actor_character_id: str | None = None
    node_binary: str | None = None
    bridge_dir: str | None = None

    @classmethod
    def from_env(cls) -> "HeadlessConfig":
        return cls(
            functions_url=normalize_functions_url(
                os.getenv("GB_FUNCTIONS_URL") or os.getenv("EDGE_FUNCTIONS_URL")
            ),
            api_token=(
                os.getenv("GB_API_TOKEN")
                or os.getenv("EDGE_API_TOKEN")
                or os.getenv("SUPABASE_API_TOKEN")
            ),
            access_token=os.getenv("GB_ACCESS_TOKEN"),
            character_id=os.getenv("GB_CHARACTER_ID"),
            actor_character_id=os.getenv("GB_ACTOR_CHARACTER_ID"),
            node_binary=os.getenv("GB_NODE_BINARY"),
            bridge_dir=os.getenv("GB_BRIDGE_DIR"),
        )
