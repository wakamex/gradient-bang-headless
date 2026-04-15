# Gradient Bang Headless

This repo is the home for a headless client and automation tooling for Gradient Bang.

## Layout

- `upstream/`: game core submodule, pinned to `git@github.com:wakamex/gradient-bang.git`
- `src/gradient_bang_headless/`: headless client scaffold
- `bridge/`: pure Node SmallWebRTC bridge for Pipecat transport

## Current Scope

This scaffold supports:

- public control-plane calls like `register`, `login`, `user_character_create`, and `start`
- generic edge-function calls against `https://api.gradient-bang.com/functions/v1`
- `events_since` polling for request/event correlation
- a text-first Node SmallWebRTC bridge in [bridge/README.md](/code/gradient/bridge/README.md)
- Python/CLI bridge integration for `smallwebrtc` session connect/request/message flows
- a hosted-browser runner for the live `game.gradient-bang.com` client
- a same-session browser sequence runner for multi-step gameplay automation
- a contract loop runner that repeats tutorial/contract advancement prompts
- a stricter hosted-browser readiness check that waits for an interactive command shell
- a command-watch mode for long-running in-game tasks
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

Copy `.env.example` or export values directly:

- `GB_FUNCTIONS_URL`: defaults to `https://api.gradient-bang.com/functions/v1`
- `GB_API_TOKEN`: trusted gameplay token for protected edge functions
- `GB_ACCESS_TOKEN`: Supabase access token returned by `login`
- `GB_CHARACTER_ID`: default player character for gameplay calls
- `GB_ACTOR_CHARACTER_ID`: optional corp-member actor when driving corp ships

## CLI

```bash
gb-headless login --email you@example.com --password 'secret'
gb-headless register --email you@example.com --password 'secret'
gb-headless confirm-url --verify-url 'https://api.gradient-bang.com/auth/v1/verify?...'
gb-headless character-list --access-token "$GB_ACCESS_TOKEN"
gb-headless character-create --name "My Pilot" --access-token "$GB_ACCESS_TOKEN"
gb-headless start-session --character-id "$GB_CHARACTER_ID" --access-token "$GB_ACCESS_TOKEN"
gb-headless signup-and-start \
  --email you@example.com \
  --password 'secret' \
  --name 'My Pilot' \
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
gb-headless browser-connect \
  --email you@example.com \
  --password 'secret' \
  --character-name 'My Pilot'
gb-headless browser-click \
  --email you@example.com \
  --password 'secret' \
  --character-name 'My Pilot' \
  --label 'Skip Tutorial'
gb-headless browser-command \
  --email you@example.com \
  --password 'secret' \
  --character-name 'My Pilot' \
  --text 'plot a safe course'
gb-headless browser-sequence \
  --email you@example.com \
  --password 'secret' \
  --character-name 'My Pilot' \
  --steps '[{"type":"command","text":"show my contracts panel"},{"type":"command","text":"find the nearest mega-port and take us there"}]'
gb-headless browser-contract-loop \
  --email you@example.com \
  --password 'secret' \
  --character-name 'My Pilot' \
  --iterations 3 \
  --wait-after-ms 60000
gb-headless browser-command-watch \
  --email you@example.com \
  --password 'secret' \
  --character-name 'My Pilot' \
  --text 'complete the next tutorial or contract step now if you can' \
  --watch-timeout-ms 300000 \
  --poll-interval-ms 15000
gb-headless call leaderboard_resources --method GET
gb-headless game-call my_status --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN"
gb-headless events-since --character-id "$GB_CHARACTER_ID" --api-token "$GB_API_TOKEN" --follow
```

## Notes

- `call` is a generic edge-function wrapper.
- `confirm-url` accepts the raw Supabase verify URL, HTML-escaped links copied from the email body, or a redirecting link that eventually lands on it.
- `game-call` auto-injects `character_id` and `actor_character_id` when configured.
- `events-since` can batch `character_ids`, `ship_ids`, and `corp_id`, and can follow the stream with polling.
- the Node bridge is text-first: it skips mic/camera capture, but still needs Node WebRTC support through `@roamhq/wrtc`.
- `session-connect`, `session-request`, `session-message`, and `session-send-text` use the Node bridge from the same `gb-headless` CLI.
- `browser-connect`, `browser-click`, and `browser-command` drive the live hosted client in headless Chromium.
- `browser-sequence` keeps one hosted browser session alive across multiple steps, which is required for reliable movement and contract progression.
- `browser-contract-loop` repeatedly submits the proven progression prompt inside one hosted session and records a status snapshot after each iteration.
- hosted-browser connect now waits for an enabled command field instead of returning during `INITIALIZING GAME INSTANCES...`.
- `browser-command-watch` is intended for long-running local tasks like travel or trading: it sends one command and then polls status until the engine settles or the watch timeout expires.
- `browser-command-watch` treats `IDLE`, `COMPLETED`, and `FAILED` as terminal states so bad plans return control immediately instead of burning the full timeout.
- the hosted client currently defaults to Daily transport in production and is the deepest proven public gameplay path so far.
- `browser-command` has been proven live for in-game text submission after the hosted client reaches control.
- `browser-sequence` has been proven live for same-session travel and the first tutorial contract step.
- `signup-and-start` is the proven public bootstrap flow:
  `register -> confirm -> login -> user_character_create -> user_character_list -> start`.
- `signup-and-start` is a practical two-pass CLI flow:
  first run without `--verify-url` to register, then rerun with the email link to finish.
