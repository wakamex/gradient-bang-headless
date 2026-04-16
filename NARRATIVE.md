# Live Narrative

This file is the running record of what the headless client has actually done
in the live Gradient Bang production game.

## Current State

- Last updated: 2026-04-15 America/Toronto
- Character: `gbheadless6039`
- Character ID: `d44df13c-ea0d-4009-aba2-b584a8708ec1`
- Corporation: `gbheadless6039 corp`
- Corporation ID: `e6c71a07-85af-4e2e-ac47-fd82bf6cef35`
- Personal ship: `gbheadless Kestrel` (`kestrel_courier`)
- Personal ship sector: `472`
- Personal ship credits: `1,471`
- Corporation fleet:
  - `gbheadless Auto Probe 1` (`autonomous_probe`) in sector `1908`
  - `gbheadless Auto Probe 20260416-0312` (`autonomous_probe`) in sector `1695`
- Completed quests:
  - `tutorial`
  - `tutorial_corporations`
- Current frontier:
  - grow the corporation beyond the tutorial with more fleet automation and funding
  - keep converting durable live-player actions into first-class headless commands
  - investigate why the exact frontend unowned-ship prompt currently misroutes to salvage
  - teach the generic loop how to stop on fleet-growth targets instead of timing out after success

## Timeline

### Fresh Bootstrap

- Registered a fresh live account through the public production flow.
- Confirmed the email through the real Supabase verify URL flow.
- Logged in, created the character `gbheadless6039`, and wrote fresh auth values into `.env`.
- Proved the public bootstrap path end to end:
  `register -> confirm -> login -> user_character_create -> start`.

### Tutorial Progression

- Reached the starter mega-port and completed the early tutorial chain headlessly.
- Claimed tutorial rewards for steps 1 through 5 with `session-claim-all-rewards`.
- Mapped the profitable starter trade route and ground credits until the Kestrel purchase was affordable.
- Bought `gbheadless Kestrel`, completing `Purchase a kestrel`.
- Accepted `tutorial_corporations` headlessly and claimed the final `tutorial` rewards.

### Corporation Setup

- Created a live corporation named `gbheadless6039 corp` through a regular player-style prompt.
- Confirmed the new corporation with `session-corporation`.
- Claimed the `Create or join a corporation` reward.

### Corporation Fleet

- Proved that a long-lived live session is enough to complete corporation-ship purchases.
- Purchased the first corporation ship, `gbheadless Auto Probe 1`.
- Added a first-class `session-corp-task` command to the client.
- Used `session-corp-task` to order `gbheadless Auto Probe 1 [eab4cd]` to travel from sector `472` to sector `1908`.
- Observed real `task.start` and `task.finish` lifecycle events for the corporation probe.
- Verified that `tutorial_corporations` completed after the successful corp-ship task.
- Claimed the final `tutorial_corporations` reward, leaving both checked-in tutorial quest lines fully completed on the live account.

### Post-Tutorial Findings

- Added a first-class `session-collect-unowned-ship` command based on the exact frontend prompt contract:
  `collect unowned ship id <id> in sector`
- Verified that sector `472` currently reports dozens of `unowned_ships` in the live status snapshot.
- Tried the exact website prompt against fresh live unowned-ship IDs.
- Current live result: the bot starts a player-ship task, routes the action to `salvage_collect`, and fails with `404 Salvage not available`.
- This means the headless client now reproduces a real live mismatch on that surface instead of merely lacking coverage.

### Fleet Growth Beyond The Tutorial

- Reused the long-lived session loop to purchase a second corporation probe after the tutorial reward payout.
- Confirmed the second fleet ship exists live as `gbheadless Auto Probe 20260416-0312`.
- Observed another real product gap: the loop succeeded at the objective but still stopped on elapsed time because it has no fleet-growth target condition yet.
- Used `session-corp-task` on the new probe and sent it from sector `472` to sector `1695`.
- Observed real `task.start` and `task.finish` lifecycle events for that second post-tutorial fleet task as well.
