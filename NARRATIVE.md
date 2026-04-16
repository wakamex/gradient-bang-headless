# Live Narrative

This file is the running record of what the headless client has actually done
in the live Gradient Bang production game.

## Current State

- Last updated: 2026-04-16 America/Toronto
- Character: `gbheadless6039`
- Character ID: `d44df13c-ea0d-4009-aba2-b584a8708ec1`
- Corporation: `gbheadless6039 corp`
- Corporation ID: `e6c71a07-85af-4e2e-ac47-fd82bf6cef35`
- Personal ship: `gbheadless Kestrel` (`kestrel_courier`)
- Personal ship sector: `3358`
- Personal ship credits: `1,205`
- Personal ship warp: `191/500`
- Corporation fleet:
  - `gbheadless Auto Hauler 1` (`autonomous_light_hauler`) in sector `472`
  - `gbheadless Auto Probe 1` (`autonomous_probe`) in sector `867`
  - destroyed historical hull: `gbheadless Auto Probe 20260416-0312`
- Visible leaderboard status:
  - exploration: on the visible board at `54` sectors visited, observed around rank `98-99`
  - wealth: off the visible board, estimated `32,205` total wealth with a current gap of about `3,440`
  - trading: still off the visible board
- Completed quests:
  - `tutorial`
  - `tutorial_corporations`
- Current frontier:
  - keep converting the newly mapped live trade ladder into a reusable headless loop
  - push wealth onto the visible board, likely by combining personal profits with corporation-ship work
  - continue climbing trading toward the visible board now that the capital base is over `1,000`
  - revisit unowned-ship recovery later; it is still the highest-leverage unresolved wealth surface

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

### Leaderboard Reconnaissance And Exploration Rank

- Added a first-class `leaderboard-self-summary` command to compare live self state against the public leaderboard.
- Verified from the upstream code and live endpoint that the website only exposes three player-facing leaderboard categories:
  `wealth`, `trading`, and `exploration`.
- Verified the important production rule split:
  - wealth includes corporation ship wealth for each member
  - exploration unions personal and corporation discovery
  - trading remains personal-only
- Used a longer `session-corp-task` exploration run to push `gbheadless Auto Probe 1 [eab4cd]` from sector `4658` through `29` new sectors and finish in sector `867`.
- The probe's route summary for that run was:
  `3094 -> 4333 -> 1417 -> 319 -> 1785 -> 1942 -> 580 -> 1333 -> 4790 -> 611 -> 1413 -> 3124 -> 1469 -> 2811 -> 1179 -> 2513 -> 596 -> 1575 -> 2891 -> 4948 -> 2892 -> 2579 -> 2881 -> 2969 -> 3918 -> 780 -> 1320 -> 1421 -> 867`
- That run pushed the live account onto the visible exploration board at `54` sectors visited.
- The exact visible rank moved slightly between refreshes, but the live public board showed it around `98-99`.

### Midgame Trading Ladder

- Added a first-class `session-player-task` command so the personal ship can run short watched objectives the same way the corporation ships already do.
- Used the live known-port graph to stop guessing and map the best route by capital band.
- Current proven route ladder is:
  - low capital: `1908 -> 3358` Retro Organics shuttle
  - mid capital from sector `674`: `674 -> 907 -> 674` NS/QF cycle
  - higher capital: `472 -> 3358` full-hold Neuro Symbolics run
- Proved the low-capital bootstrap directly:
  - `1908` sold RO at `8`, then later `9`
  - `3358` bought RO at `12`
  - repeated shuttle runs grew the ship from `157` to `233`, then to `349`, then to `529` credits
- Proved the mid-capital cycle directly:
  - `674` sold NS at `42`
  - `907` bought NS at `46` and sold QF at `19`
  - `674` bought QF at `25`
  - one full `674 -> 907 -> 674` loop grew credits from `691` to `935`
- Proved the higher-capital handoff directly:
  - with `935` credits on hand, bought a full `30` Neuro Symbolics at sector `472`
  - sold all `30` at sector `3358`
  - finished at `1,205` credits with `191` warp in sector `3358`
- The headless client is now no longer just replaying the tutorial route. It has a live-tested economic ladder that changes with capital and current location.

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
