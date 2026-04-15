# Gradient Bang Headless

This repo is the home for a headless client and automation tooling for Gradient Bang.

## Layout

- `upstream/`: game core submodule, pinned to `git@github.com:wakamex/gradient-bang.git`
- `src/gradient_bang_headless/`: headless client scaffold

## Current Scope

This scaffold supports:

- public control-plane calls like `login` and `user_character_create`
- generic edge-function calls against `https://api.gradient-bang.com/functions/v1`
- `events_since` polling for request/event correlation
- a bridge into `upstream/` so trusted tooling can reuse `gradientbang.utils.supabase_client.AsyncGameClient`

## Important Constraint

The live game client uses `https://api.gradient-bang.com/functions/v1/start`.
Most gameplay edge functions are still protected by `X-API-Token`, so a public headless client still needs a scoped gameplay-session/token flow before it can safely call gameplay endpoints directly.

## Setup

```bash
git submodule update --init --recursive
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Environment

Copy `.env.example` or export values directly:

- `GB_FUNCTIONS_URL`: defaults to `https://api.gradient-bang.com/functions/v1`
- `GB_API_TOKEN`: trusted gameplay token for protected edge functions
- `GB_ACCESS_TOKEN`: Supabase access token returned by `login`
- `GB_CHARACTER_ID`: default player character for gameplay calls
- `GB_ACTOR_CHARACTER_ID`: optional corp-member actor when driving corp ships

## CLI

```bash
gb-headless login --email you@example.com --password 'secret'
gb-headless character-list --access-token "$GB_ACCESS_TOKEN"
gb-headless character-create --name "My Pilot" --access-token "$GB_ACCESS_TOKEN"
gb-headless call leaderboard_resources --method GET
gb-headless game-call my_status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless events-since --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN" --follow
```

## Notes

- `call` is a generic edge-function wrapper.
- `game-call` auto-injects `character_id` and `actor_character_id` when configured.
- `events-since` can batch `character_ids`, `ship_ids`, and `corp_id`, and can follow the stream with polling.
