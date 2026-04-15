from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DEFAULT_FUNCTIONS_URL = "https://api.gradient-bang.com/functions/v1"
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def dotenv_path() -> Path:
    return repo_root() / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


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


def update_dotenv(
    updates: Mapping[str, str | None],
    *,
    path: Path | None = None,
) -> Path:
    target = path or dotenv_path()
    lines = target.read_text().splitlines() if target.exists() else []
    pending = dict(updates)
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue

        key, _old_value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key not in pending:
            output.append(line)
            continue

        output.append(f"{normalized_key}={_format_dotenv_value(pending.pop(normalized_key))}")

    if pending and output and output[-1] != "":
        output.append("")

    for key, value in pending.items():
        output.append(f"{key}={_format_dotenv_value(value)}")

    target.write_text("\n".join(output) + "\n")
    return target


def _format_dotenv_value(value: str | None) -> str:
    if value is None:
        return ""
    rendered = str(value)
    if any(ch in rendered for ch in {" ", "\t", "\n", '"', "'"}) or rendered.startswith("#"):
        escaped = rendered.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return rendered


@dataclass(slots=True)
class HeadlessConfig:
    functions_url: str
    api_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    character_id: str | None = None
    actor_character_id: str | None = None
    email: str | None = None
    password: str | None = None
    character_name: str | None = None
    node_binary: str | None = None
    bridge_dir: str | None = None

    @classmethod
    def from_env(cls) -> "HeadlessConfig":
        _load_dotenv(dotenv_path())
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
            refresh_token=os.getenv("GB_REFRESH_TOKEN"),
            character_id=os.getenv("GB_CHARACTER_ID"),
            actor_character_id=os.getenv("GB_ACTOR_CHARACTER_ID"),
            email=os.getenv("GB_EMAIL"),
            password=os.getenv("GB_PASSWORD"),
            character_name=os.getenv("GB_CHARACTER_NAME"),
            node_binary=os.getenv("GB_NODE_BINARY"),
            bridge_dir=os.getenv("GB_BRIDGE_DIR"),
        )
