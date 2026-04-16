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
- Personal ship credits: `31`
- Corporation fleet:
  - `gbheadless Auto Hauler 1` (`autonomous_light_hauler`) in sector `472`
  - `gbheadless Auto Probe 1` (`autonomous_probe`) in sector `692`
  - destroyed historical hull: `gbheadless Auto Probe 20260416-0312`
- Completed quests:
  - `tutorial`
  - `tutorial_corporations`
- Current frontier:
  - determine whether unowned-ship collection is a live prompt-path bug or a recoverable client-side mismatch
  - start giving the new light hauler productive work instead of leaving it parked at the megaport
  - keep probing live post-tutorial exploration for new contracts, better routes, or richer midgame loops
  - keep converting durable live-player actions into first-class headless commands as they are proven

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

### Post-Tutorial Combat, Salvage, And Garrison

- Reached first live combat through the session surface by engaging `Rix` in-sector.
- Submitted a real first-class `combat-action` and received a live `combat.round_resolved`.
- Collected live salvage through the exact frontend salvage surface.
- Proved a full live garrison cycle:
  - deployed fighters into a garrison
  - switched the garrison to toll mode
  - collected the fighters back successfully

### Trade Route Hardening

- Mapped and reused the profitable live `Neuro Symbolics` route between sector `472` and sector `3358`.
- Found a real race in the original player-task watcher: trade prompts could be credited with an older movement task finish.
- Reworked the task watcher so it binds to the first new `task.start` and only accepts the matching `task.finish`.
- Re-ran the route after the fix and grew credits cleanly from the low thousands to `5,031`.

### Fleet Growth Beyond The Tutorial

- Converted the `5,031` credit balance into the first non-probe corporation ship:
  `gbheadless Auto Hauler 1`.
- Verified the corporation fleet as a more useful mix than the tutorial baseline:
  one light hauler plus one active probe.
- Proved that the loop runner now stops on real fleet-growth targets by exiting successfully on `autonomous_light_hauler` count.

### Exploration Through Corporation Tasks

- Reused `session-corp-task` after the tutorials to push the surviving probe deeper into the map.
- Sent `gbheadless Auto Probe 1 [eab4cd]` from sector `1908` to sector `692`.
- Observed real `task.start` and `task.finish` for that post-tutorial corp exploration task.
- Found a useful verification nuance:
  - `ships.list` reflected the probe at sector `692` immediately
  - `corporation.data` still lagged on the older sector right after task completion

### Post-Tutorial Findings

- Asked the live bot for further normal-player goals after finishing the tutorial lines.
- Current live answer is consistent: the tutorial contracts are done and no further obvious contract is being surfaced through the regular player path yet.

- Added a first-class `session-collect-unowned-ship` command based on the exact frontend prompt contract:
  `collect unowned ship id <id> in sector`
- Verified that sector `472` currently reports dozens of `unowned_ships` in the live status snapshot.
- Tried the exact website prompt against fresh live unowned-ship IDs.
- Current live result: the bot starts a player-ship task, treats the request like salvage lookup, and fails with `404 Salvage not available`.
- This is now a documented live production mismatch, not just an unimplemented client surface.

## Personal Impressions

From this headless playthrough, the game is more interesting than a conventional space-trading grind because the interface is part of the game. The strongest idea here is that progress comes from learning how to drive an agent-mediated world, not just from clicking faster through menus.

The parts I like most are the moments where the systems click together: buying into a better ship, forming a corporation, then tasking autonomous probes and seeing real `task.start` and `task.finish` events come back from the live world. That makes the game feel less like a static economy sim and more like a lightweight operations sandbox.

The rough edges are very visible. Some surfaces are elegant when they work, but others are brittle, ambiguous, or route to the wrong backend behavior, as with the current unowned-ship collection mismatch. That said, those edges are also revealing: they make it clear where the game is genuinely systemic and where it is still held together by prompt conventions and hidden assumptions.

Overall impression: the core idea is strong. It feels novel, a little weird in a good way, and substantially more interesting than the average browser game because the player is effectively learning how to operate an in-world organization through language and automation.
