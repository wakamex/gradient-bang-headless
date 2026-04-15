# Headless Client Plan

This file tracks the execution plan for pushing the Gradient Bang headless
client as far into live gameplay as possible.

The intent is not just to scaffold code, but to keep a running record of:

- what the client can do now,
- what has been proven against production,
- what the next feature commit is,
- what is currently blocked,
- and what fallback path to take when a transport or API path stalls.

## Goal

Reach the deepest playable headless path available from the public production
surface at `https://api.gradient-bang.com/functions/v1`, while committing each
incremental capability along the way.

## Proven Production Surface

These flows have already been proven live:

- `register`
- email confirmation through Supabase verify URLs
- `login`
- `user_character_create`
- `user_character_list`
- `start`

That means the public control plane is real and usable today.

## Current Capability Map

### Control Plane

Implemented and production-proven:

- account registration
- email verification URL resolution
- login
- character creation
- character visibility polling
- session creation through `/start`

### Protected Edge Functions

Implemented for trusted use only:

- generic gameplay function calls with `X-API-Token`
- `events_since` polling

These are not the public path for a player-distributed headless client.

### Session Transport

In progress:

- `smallwebrtc` bridge process in Node
- JSON-lines bridge protocol
- Node WebRTC globals via `@roamhq/wrtc`
- Python wrapper for the bridge process
- CLI session commands for bridge-driven connect/request/message/text flows
- production path reaches:
  `start -> /start/{sessionId}/api/offer -> connecting`

Not yet proven:

- Pipecat `bot_ready`
- transport-level command exchange after WebRTC connect

## Planned Commit Sequence

### 1. Plan And Feature Ledger

Commit scope:

- add this file
- document what is proven, what is blocked, and what comes next

Success condition:

- repo contains a concrete execution plan and feature ledger

### 2. Python Bridge Integration

Commit scope:

- add Python wrapper for the `bridge/` process
- add CLI commands to drive bridge operations
- make the bridge usable from the same `gb-headless` entrypoint

Success condition:

- user can start the bridge, connect, send client messages, request status,
  and close it from Python/CLI without hand-writing raw JSON

### 3. Headless Session Actions

Commit scope:

- add first-class actions for RTVI/game control messages:
  - `start`
  - `get-my-status`
  - `get-known-ports`
  - `user-text-input`
  - `skip-tutorial`

Success condition:

- if the transport is connected, these actions are reachable from CLI/Python

### 4. Transport Investigation

Commit scope:

- keep pushing pure Node `smallwebrtc`
- instrument offer/connect phases
- tighten timeouts and error reporting
- test live against production after each meaningful change

Success condition:

- either reach `bot_ready`, or reduce the remaining gap to a single clear issue

### 5. Browser-Hosted Fallback Bridge

Commit scope:

- only if pure Node remains stalled
- implement a browser-hosted bridge that preserves the same JSON protocol
- keep mic/camera logically off; use the browser only for transport/runtime

Success condition:

- reach `bot_ready` and begin sending headless game actions over the session

## Definition Of “As Far As Possible”

For this repo, “as far as possible” means:

1. bootstrap a real user and character
2. create a real bot/session
3. connect transport
4. exchange real client messages
5. retrieve live in-game state
6. submit live in-game actions that the session path allows

If a phase is blocked, the next commit should improve one of:

- reachability,
- observability,
- ergonomics,
- or fallback execution path.

## Current Blockers

### Pure Node `smallwebrtc` Stall

Observed production behavior:

- `start` succeeds
- `/start/{sessionId}/api/offer` request is issued
- transport reaches `connecting`
- `bot_ready` never arrives under the pure Node path

Current mitigation:

- bridge-level `connectTimeoutMs`
- bridge-level `requestTimeoutMs`
- clean disconnect on timeout

### Public Gameplay API Access

Most direct gameplay edge functions still require `X-API-Token`.

That means the public player path should continue to prioritize the bot/session
surface over direct edge-function gameplay calls.

## Immediate Next Step

Keep pushing transport reachability with the new Python/CLI bridge integration,
then add first-class session action helpers and continue testing production
paths until the next real blocker is isolated.
