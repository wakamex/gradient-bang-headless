# Headless Rules

These rules exist to keep the headless client biased toward stable backend paths and away from brittle browser automation, while staying scoped to what a regular website player can actually do.

## Core Rules

1. Keep the supported headless client surface browser-free.
2. Start from `upstream/` source code before inspecting live traffic.
3. Classify every interaction into one of three buckets:
   - local UI only
   - Pipecat session client message
   - direct edge-function RPC
4. Prefer direct edge-function calls over browser clicks whenever a feature bottoms out in `_request("...")`.
5. Prefer direct Pipecat session messages over browser clicks whenever the frontend uses `client.sendClientMessage(...)`.
6. If browser work is ever used during investigation, keep it outside the supported client surface and treat it as one-off diagnostics only.
7. Do not assume a visible button means there is a dedicated HTTP endpoint for that button.
8. Confirm uncertain mappings with live traces only after reading the code path.
9. When a mapping is proven, write it down in docs or code comments so the browser does not become the default again.

## Player Scope

1. The product goal is parity with a normal logged-in website player, headlessly, and nothing more.
2. In scope: anything a regular player can reach through public auth, `/start`, and the session transport/message surface.
3. Out of scope for the shipped client: admin endpoints, operator credentials, service-role keys, `GB_API_TOKEN`, and any direct secret-backed gameplay RPCs unavailable to regular players.
4. Secret-backed edge functions may still be traced to understand server semantics, but the shipped client must not depend on them.

## Canonical Trace Method

For any frontend action, follow this chain:

1. Find the React handler in `upstream/client/app/src/...`.
2. Check whether it goes through `dispatchAction(...)` or `client.sendClientMessage(...)`.
3. Resolve the message name in `upstream/src/gradientbang/pipecat_server/client_message_handler.py`.
4. Find the corresponding `AsyncGameClient` method in `upstream/src/gradientbang/utils/api_client.py`.
5. If that method calls `_request("foo.bar", payload)`, infer the Supabase edge path as `/functions/v1/foo_bar`.
6. Confirm with a live request only if the code path is ambiguous or runtime behavior disagrees.

## Naming Rule

Supabase transport converts request names by replacing dots with underscores:

- `quest.assign` -> `/functions/v1/quest_assign`
- `quest.claim.reward` -> `/functions/v1/quest_claim_reward`

Source: `upstream/src/gradientbang/utils/supabase_client.py`

## Proven Examples

### Session Message -> Edge Function

- `assign-quest`
  - frontend dispatch: `upstream/client/app/src/components/dialogs/QuestList.tsx`
  - server handler: `_handle_assign_quest`
  - client method: `assign_quest(...)`
  - backend request: `quest.assign`
  - inferred edge path: `/functions/v1/quest_assign`

- `claim-step-reward`
  - frontend dispatch: `upstream/client/app/src/components/panels/ContractsPanel.tsx`
  - server handler: `_handle_claim_step_reward`
  - client method: `claim_quest_step_reward(...)`
  - backend request: `quest.claim.reward`
  - inferred edge path: `/functions/v1/quest_claim_reward`

### Local UI Only

- `Contracts`
- `Contract Board`

These open UI panels or modals. They are not the real gameplay operation. The real operations behind that UI are the semantic actions, such as `assign-quest` or `claim-step-reward`.

## Practical Bias

When adding a new headless feature, default in this order:

1. public player edge-function method
2. public player Pipecat session message
3. temporary off-path diagnostics only, never the shipped feature path

If a feature currently seems to need the browser, the next question should be: "What semantic action is this UI actually triggering?"

## Credentials And Config

1. Keep local login credentials and tokens in the repo-root `.env`.
2. Keep the tracked `.env.example` as the canonical list of required variables for setup.
3. Load defaults from `.env` in the client instead of hardcoding credentials into commands, code, or docs.
4. Treat `.env.example` as documentation and interface contract, not a place for real secrets.
5. Add new auth or session variables to `.env.example` as soon as a feature depends on them.
6. Prefer stable names under the `GB_` prefix for all headless-client configuration.

Current expected variables include:

- `GB_FUNCTIONS_URL`
- `GB_EMAIL`
- `GB_PASSWORD`
- `GB_CHARACTER_NAME`
- `GB_API_TOKEN`
- `GB_ACCESS_TOKEN`
- `GB_REFRESH_TOKEN`
- `GB_CHARACTER_ID`
- `GB_ACTOR_CHARACTER_ID`

## Local Vs Live Authority

1. Do not assume a local bot or transport server can advance a live character by itself.
2. If the client is pointed at the live production project, secret-backed gameplay still requires credentials that regular players do not have.
3. A local session-control API only removes the WebRTC and browser dependency. It does not remove the live gameplay auth boundary.
4. The product goal is live production player parity. A fully local stack is not a substitute goal.
5. Local servers, local bots, or local transports are only in scope when they directly help one of:
   - reproduce a live transport failure
   - isolate a protocol mismatch
   - prototype an interface that can also be used against live production
6. Do not spend feature work on local-only gameplay surfaces or secret-backed production surfaces that cannot plausibly be applied to the live player path.
7. Before investing in local transport or server work, write down exactly how that work is expected to unblock live production control.

## Key Files

- `upstream/client/app/src/stores/game.ts`
- `upstream/client/app/src/types/actions.ts`
- `upstream/src/gradientbang/pipecat_server/client_message_handler.py`
- `upstream/src/gradientbang/utils/api_client.py`
- `upstream/src/gradientbang/utils/supabase_client.py`
- `.env.example`
- `src/gradient_bang_headless/config.py`
