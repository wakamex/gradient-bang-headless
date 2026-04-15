# Gradient Bang Headless

This repo is the home for a headless client and automation tooling for Gradient Bang.

## Layout

- `upstream/`: game core submodule, pinned to `git@github.com:wakamex/gradient-bang.git`
- `src/gradient_bang_headless/`: headless client scaffold
- `bridge/`: pure Node WebRTC bridge for Pipecat transport

## Current Scope

This scaffold supports:

- public control-plane calls like `register`, `login`, `user_character_create`, and `start`
- named protected gameplay calls for trusted use
- generic edge-function calls against `https://api.gradient-bang.com/functions/v1`
- `events_since` polling for request/event correlation
- a text-first raw Node WebRTC bridge in [bridge/README.md](/code/gradient/bridge/README.md)
- Python/CLI bridge integration for session connect/request/message flows
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

cd bridge
npm install
```

## Environment

The CLI auto-loads a repo-root `.env` if present. Copy `.env.example` or export
values directly:

- `GB_FUNCTIONS_URL`: defaults to `https://api.gradient-bang.com/functions/v1`
- `GB_EMAIL`: default login email for public/bootstrap flows
- `GB_PASSWORD`: default login password for public/bootstrap flows
- `GB_CHARACTER_NAME`: default character name for bootstrap flows
- `GB_API_TOKEN`: trusted gameplay token for protected edge functions
- `GB_ACCESS_TOKEN`: Supabase access token returned by `login`
- `GB_REFRESH_TOKEN`: Supabase refresh token returned by `login`
- `GB_CHARACTER_ID`: default player character for gameplay calls
- `GB_ACTOR_CHARACTER_ID`: optional corp-member actor when driving corp ships

## CLI

```bash
gb-headless login
gb-headless auth-sync
gb-headless register
gb-headless login --email you@example.com --password 'secret'
gb-headless auth-sync --character-name "$GB_CHARACTER_NAME"
gb-headless register --email you@example.com --password 'secret'
gb-headless confirm-url --verify-url 'https://api.gradient-bang.com/auth/v1/verify?...'
gb-headless character-list --access-token "$GB_ACCESS_TOKEN"
gb-headless character-create --access-token "$GB_ACCESS_TOKEN"
gb-headless start-session --access-token "$GB_ACCESS_TOKEN"
gb-headless signup-and-start \
  --verify-url 'https://api.gradient-bang.com/auth/v1/verify?...'
gb-headless session-connect --character-id "$GB_CHARACTER_ID" --access-token "$GB_ACCESS_TOKEN"
gb-headless session-request \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --message-type get-my-status
gb-headless session-message \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --message-type start
gb-headless session-send-text \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --content 'plot a safe course'
gb-headless session-status \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-known-ports \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN"
gb-headless session-assign-quest \
  --character-id "$GB_CHARACTER_ID" \
  --access-token "$GB_ACCESS_TOKEN" \
  --quest-code tutorial_corporations
gb-headless call leaderboard_resources --method GET
gb-headless status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless plot-course --to-sector 301 --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless known-ports --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless quest-status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless game-call my_status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless events-since --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN" --follow
```

## Notes

- `call` is a generic edge-function wrapper.
- `status`, `move`, `plot-course`, `map-region`, `known-ports`, `trade`,
  `recharge-warp`, `purchase-fighters`, `ship-definitions`, `ship-purchase`,
  `quest-status`, `quest-assign`, and `quest-claim-reward` are the preferred
  trusted gameplay commands over raw `game-call`.
- `session-status`, `session-known-ports`, `session-task-history`,
  `session-map`, `session-assign-quest`, `session-claim-reward`,
  `session-cancel-task`, `session-skip-tutorial`, and `session-user-text`
  follow the frontend's real message -> event pattern and are preferred over
  hand-written `session-message` payloads.
- `.env` values are used automatically for login/session defaults, so the
  shortest commands can omit repeated credentials.
- `auth-sync` is the shortest way to populate runtime auth state in `.env`:
  it logs in, writes `GB_ACCESS_TOKEN` and `GB_REFRESH_TOKEN`, and writes
  `GB_CHARACTER_ID` when it can select a character by configured name or
  by a single-character account.
- `confirm-url` accepts the raw Supabase verify URL, HTML-escaped links copied from the email body, or a redirecting link that eventually lands on it.
- `game-call` auto-injects `character_id` and `actor_character_id` when configured.
- `events-since` can batch `character_ids`, `ship_ids`, and `corp_id`, and can follow the stream with polling.
- the Node bridge is text-first: it skips mic/camera capture, but still needs Node WebRTC support through `@roamhq/wrtc`.
- `session-connect`, `session-request`, `session-message`, and `session-send-text` use the Node bridge from the same `gb-headless` CLI.
- the preferred order is: direct edge-function method, then direct session message.
- browser-driven gameplay is intentionally not part of the supported client surface in this repo.
- the current public bridge bootstraps with `start(createDailyRoom=true)` and reaches transport `ready` in pure Node.
- Pipecat app-level frames are still blocked: the public bridge does not yet receive `bot_ready` or gameplay server events after connect.
- `signup-and-start` is the proven public bootstrap flow:
  `register -> confirm -> login -> user_character_create -> user_character_list -> start`.
- `signup-and-start` is a practical two-pass CLI flow:
  first run without `--verify-url` to register, then rerun with the email link to finish.
