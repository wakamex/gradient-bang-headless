from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import HeadlessConfig, repo_root, supabase_root_from_functions_url


def upstream_root() -> Path:
    return repo_root() / "upstream"


def upstream_src() -> Path:
    return upstream_root() / "src"


def ensure_upstream_import_path() -> Path:
    src = upstream_src()
    if not src.is_dir():
        raise RuntimeError(
            f"Upstream source tree not found at {src}. "
            "Run `git submodule update --init --recursive` first."
        )
    src_str = str(src)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    return src


def load_async_game_client():
    ensure_upstream_import_path()
    from gradientbang.utils.supabase_client import AsyncGameClient

    return AsyncGameClient


def build_upstream_game_client(
    config: HeadlessConfig,
    *,
    character_id: str,
    actor_character_id: str | None = None,
    enable_event_polling: bool = False,
):
    AsyncGameClient = load_async_game_client()
    supabase_root = supabase_root_from_functions_url(config.functions_url)

    os.environ.setdefault("SUPABASE_URL", supabase_root)
    os.environ.setdefault("EDGE_FUNCTIONS_URL", config.functions_url)

    if config.api_token:
        os.environ.setdefault("EDGE_API_TOKEN", config.api_token)
    if config.access_token:
        os.environ.setdefault("GB_ACCESS_TOKEN", config.access_token)

    return AsyncGameClient(
        base_url=supabase_root,
        character_id=character_id,
        actor_character_id=actor_character_id,
        transport="supabase",
        enable_event_polling=enable_event_polling,
    )
