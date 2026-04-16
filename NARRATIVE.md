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
- Personal ship sector: `3124`
- Personal ship credits: `6,187`
- Personal ship warp: `377/500`
- Corporation fleet:
  - `gbheadless Auto Hauler 1` (`autonomous_light_hauler`) stranded in sector `2204` with `0/500` warp
  - `gbheadless Auto Probe 1` (`autonomous_probe`) stranded in sector `3341` with `0/500` warp
  - `gbheadless Auto Probe I` (`autonomous_probe`) active in sector `2984` with `473/500` warp
  - destroyed historical hull: `gbheadless Auto Probe 20260416-0312`
- Visible leaderboard status:
  - exploration: on the visible board at `319` known sectors, currently observed at rank `37`
  - wealth: on the visible board, currently observed at rank `69` with visible row value `42,787`
  - trading: on the visible board, currently observed at rank `28` with `245,438` total trade volume across `281` trades
- Completed quests:
  - `tutorial`
  - `tutorial_corporations`
- Current frontier:
  - keep all three leaderboard categories visible while climbing deeper into each board
  - use repeated corporation-probe frontier loops as the primary exploration engine
  - use port-code-aware, map-backed route selection instead of naive price comparisons
  - use `session-auto-trade-loop --goal wealth` for the best visible profit-per-hop route and `--goal trading` for the best visible volume-per-hop route, but only after validating that the route is legal under port `B`/`S` directionality
  - use `session-wealth-loadout` when the ship is parked on a cheap legal seller and the immediate goal is wealth-board rank instead of realized profit
  - use exact move-and-trade prompt contracts once the ship is on a valid port; invalid trade routes can silently stall even when the quoted price looks profitable
  - use cheap cargo as a wealth-board lever, because the live leaderboard currently values cargo at a flat `100` credits per unit
  - prefer fresh `1000`-credit autonomous probes over long rescue chains when the goal is exploration rank
  - keep compounding toward the first meaningful personal ship upgrade beyond the `Kestrel Courier`, but accept that the personal ship is now being used as a rotating wealth/trading shuttle around sector `1413`
  - keep trade loops chunked and observable; large blind route batches are productive but still too opaque to count as a clean bounded surface

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
- Pushed the ladder one step further with a repeated full-hold `472 <-> 3358` Neuro Symbolics loop:
  - started from `1,205` credits at sector `3358`
  - completed `3` full `30 NS` buy/sell runs
  - stopped at sector `472` when warp fell below the configured threshold
  - final live state after that repetition was `2,015` credits and `149` warp

### Logistics Surfaces And Leaderboard Strategy

- Added first-class `session-recharge-warp` and `session-transfer-credits` commands after proving both flows live:
  - recharged the personal ship to full at the mega-port in sector `472`
  - transferred credits directly to `gbheadless Auto Hauler 1`
- Read the upstream leaderboard SQL to stop optimizing blindly:
  - `exploration` unions personal and corporation map knowledge
  - `wealth` includes the full corporation fleet
  - `trading` is personal-only and ranked by 7-day `total_trade_volume`
- That changed the live strategy:
  - corporation probes handle exploration
  - the personal ship chases repeated high-priced volume
  - wealth rises as a side effect of trading profits and existing corp assets
- The older `674 -> 907 -> 674` route degraded when sector `674` stopped reliably selling the return-leg commodity, so broad freeform trade prompts were demoted.
- Added `session-trade-route-loop` as the durable replacement: a fixed `move -> buy -> move -> sell` runner built from watched player tasks.
- The first validation cycle on the live `3786 -> 1009` route succeeded exactly as intended:
  - buy `30` Neuro Symbolics at sector `3786`
  - return to sector `1009`
  - sell all `30` for a clean `+150` credits

### Visible Leaderboards

- Used a `10`-sector probe exploration task from sector `3348` to sector `4633`, pushing total known sectors from `59` to `69`.
- Ran the first long deterministic trade push on the live `3786 -> 1009` Neuro Symbolics route.
  - the first long run completed `9` cycles before a single move task failed
  - despite the stop, it still raised the personal ship from `3,307` to `4,177` credits
  - this exposed the need for step retries inside the route loop
- Hardened `session-trade-route-loop` with per-step retries, then sent the probe out again for `15` more new sectors, ending in sector `446`.
- Ran a retried `6`-cycle personal trade loop that finished cleanly:
  - `+630` credits
  - `36` warp spent
  - final state `4,807` credits at sector `1009`
- Finished with a short `2`-cycle wealth push:
  - `+180` credits
  - final state `4,987` credits and `278` warp at sector `1009`
- Latest confirmed live leaderboard state:
  - exploration visible at rank `77`
  - wealth visible at rank `92`
  - trading visible at rank `49` with `123,386` volume across `141` trades
- At this point the account is visibly represented on all three regular-player leaderboard categories through the headless client alone.

### Auth Hardening And Continued Climb

- Traced the recurring session-auth instability to the client, not to the live game:
  - repo-root `.env` was loaded with `setdefault`, so stale inherited `GB_*` vars could outrank freshly synced tokens
  - long play sessions would then hit `/start` `401` failures until a manual inline token was supplied
- Reworked the client so:
  - repo-root `.env` is authoritative for `GB_*` credentials
  - session commands auto-login and retry once when `/start` fails with `401`
- Verified the fix the useful way: by resuming normal default-path session commands without manually injecting a token.
- Used the stabilized client for another real progression wave:
  - sent `gbheadless Auto Probe 1` on a `21`-sector exploration run from sector `446` to sector `2864`
  - pushed the personal ship through another trading burst on the `3786 -> 1009` Neuro Symbolics loop
  - cleaned up the ending state by explicitly selling the last loaded hold at sector `1009`
- Latest confirmed live state after that pass:
  - `105` total known sectors
  - `5,047` personal ship credits
  - `230` warp
- Latest confirmed leaderboard movement:
  - exploration improved from rank `77` to rank `67`
  - trading improved from rank `49` to rank `40`
  - wealth stayed visible at rank `92`
- The current best proven live strategy is now explicit:
  - exploration: long corp-probe runs from the frontier
  - trading: repeated `3786 <-> 1009` Neuro Symbolics cycles
  - wealth: let the same personal trading loop compound while keeping corp assets online

### Probe Loop And Exact Trade Orders

- Added a first-class `session-corp-explore-loop` wrapper after the repeated probe runs became routine enough to deserve a real surface.
- The first pass exposed a client bug, not a game bug:
  - corp-ship matching ignored the outer `server_message` wrapper around `ships.list`
  - fixing that made the loop usable against the live probe
- The next pass exposed a more subtle live/runtime issue:
  - some successful probe tasks advanced the ship and map state without delivering a timely `task.finish`
  - the loop was hardened to treat observed sector/map progress as success instead of failing just because one lifecycle event was late
- That produced a clean series of live probe pushes:
  - `2864 -> 2071 -> 852`
  - `852 -> 72`
  - `72 -> 2554`
- Those runs pushed the live account from:
  - `105` known sectors at exploration rank `67`
  - to `147` known sectors at rank `54`
  - then to `167` known sectors at rank `48`
  - then to `189` known sectors at rank `46`
- On the personal-ship side, the old deterministic trade loop still had a brittle edge:
  - it could advance real trade volume and credits
  - but the generic `sell all` prompt sometimes unloaded only part of the hold and left the ship mid-position
- That changed the trading strategy.
  - the client now records port prices in the live status summary
  - the route loop now builds exact frontend-style trade orders instead of vague `buy max` / `sell all` prompts whenever it has the live price and quantity
  - the route loop also polls `status.snapshot` for state changes instead of waiting blindly for every `task.finish`
- The strongest proof in this pass came from the direct exact-order surface:
  - a precise `SELL 9 Neuro Symbolics @ 40` order did not just sell in place
  - the live bot routed the ship from sector `1009` to sector `3246`
  - it sold the full remainder at `45` credits each and completed cleanly with a real `task.finish`
- That is a meaningful strategy upgrade:
  - exploration is best driven by cheap autonomous probes
  - trading is starting to look better as price-constrained orders than as a single fixed destination route
  - wealth still lags because it follows realized profits and visible assets, so it remains the slowest board for now

### Live Route Ranking And Split Strategy

- Added a first-class `session-trade-opportunities` command so the client can rank the current known-port graph instead of relying on one remembered grind route.
- On the live graph from sector `3246`, the best visible routes split by goal:
  - best raw profit: `3236 -> 907` Neuro Symbolics
  - best profit per hop: `318 -> 3246` Quantum Foam
  - best trade volume per hop: `318 -> 3246` Neuro Symbolics
- That gave a cleaner answer to the user’s leaderboard question than the old one-route mentality:
  - exploration should keep using corp-probe frontier loops
  - wealth should follow the short-hop QF route
  - trading should follow the short-hop NS route
- Proved the wealth-focused side first:
  - ran `4` full QF cycles on `318 -> 3246`
  - finished cleanly at `5,539` credits and `92` warp
  - moved wealth from rank `91` to rank `86`
  - moved trading volume from `184,388` to `191,018`
- Then proved the trade-volume side:
  - ran `3` full NS cycles on `318 -> 3246`
  - finished cleanly at `5,809` credits and `74` warp
  - moved trading from rank `31` to rank `29`
  - moved wealth again from rank `86` to rank `84`
- With the personal ship’s warp now lower, the probe became the obvious next lever again.
  - sent one `20`-sector run from `2554 -> 1399`
  - then another `20`-sector run from `1399 -> 2695`
  - that pushed exploration from rank `46` to rank `43`
  - total known sectors rose from `189` to `229`
- The important strategic change is that the client is no longer just "good at one route."
  It can now rank the live visible market graph and choose different loops for different leaderboard goals.

### Map-Backed Auto Trading

- The first version of `session-trade-opportunities` still had one weak assumption:
  it estimated inter-port distance from the difference in each port's `hops_from_start`.
- The live `session-map` surface exposed a better foundation.
  It returns the actual sector graph with lanes and `hops_from_center`, which is enough to run real shortest-path calculations.
- Reworked the trade helper to use that graph.
  That immediately corrected one of the earlier conclusions:
  - the better wealth route from sector `3246` was not the short local QF hop
  - it was `3786 -> 3236` on Quantum Foam, because the graph showed the inter-port distance was only `1`
- Added `session-auto-trade-loop` as the next durable layer:
  - `--goal wealth` picks the best current profit-per-hop route
  - `--goal trading` picks the best current trade-volume-per-hop route
  - `--goal profit` picks the best raw-profit route
- Proved the wealth path live first:
  - `session-auto-trade-loop --goal wealth --max-cycles 2`
  - selected `3786 -> 3236` on Quantum Foam
  - finished cleanly at `6,229` credits and `59` warp
  - improved wealth from rank `84` to rank `83`
- Then proved the trading path enough to find the next weakness:
  - `session-auto-trade-loop --goal trading --max-cycles 2`
  - selected `3236 -> 318` on Neuro Symbolics
  - it bought the full hold and moved correctly, but stopped dirty on the sell edge case again
- That led to one more useful hardening pass:
  - added a final exact trade-order sell recovery inside the route loop
  - used the current dirty hold as the live test case
  - the loop successfully unwound the stuck position, emptied the hold, and improved credits instead of leaving the ship stranded with cargo
- Current effect of that work:
  - route choice is now goal-driven and graph-backed
  - wealth is up to rank `83`
  - trading remains at rank `29`, but total volume rose again to `204,638`
- The exploration side kept compounding in parallel:
  - one probe run needed a retry with `--connect-timeout-ms 40000` after Daily connected but the browser bridge timed out on its ready gate
  - after the retry, the probe finished another `11` new sectors: `2695 -> 3792`
  - total known sectors rose to `240`

### Goal-Driven Loops And Recovery

- Tightened the route-loop accounting after the first `session-auto-trade-loop --goal wealth` pass.
  The trade-order sell recovery was doing the important gameplay work, but the loop result undercounted it as `0` completed cycles.
- Fixed that, then revalidated it live:
  - `session-auto-trade-loop --goal wealth --max-cycles 1`
  - selected `3786 -> 3236` on Quantum Foam from the live map-backed graph
  - now reports `1` completed cycle correctly
  - raised visible wealth from rank `83` to rank `79`
- The auto-trade loop is now good enough that the client can pick a leaderboard goal and turn it into actual play without manual route transcription.
- One caveat remains:
  - the trading goal still leans on the same underlying sell surface
  - the final exact trade-order recovery now rescues that state usefully, but the clean path is still more reliable for wealth pushes than for pure volume pushes
- Parallel exploration stayed the better bargain:
  - a follow-up probe run added `17` sectors
  - another added `13` more
  - total known sectors climbed from `240` to `272`
  - exploration rank improved from `43` to `39`
- There is still one visibility mismatch worth keeping in mind:
  - the last probe-loop result reported a different end sector than a later standalone `session-ships` read
  - that means post-task probe location should still be treated as eventually consistent across surfaces, even after the earlier task-watching fixes

### Post-Tutorial Findings

- Asked the live bot for further normal-player goals after finishing the tutorial lines.
- Current live answer is consistent: the tutorial contracts are done and no further obvious contract is being surfaced through the regular player path yet.

- Added a first-class `session-collect-unowned-ship` command based on the exact frontend prompt contract:
  `collect unowned ship id <id> in sector`
- Verified that sector `472` currently reports dozens of `unowned_ships` in the live status snapshot.
- Tried the exact website prompt against fresh live unowned-ship IDs.
- Current live result: the bot starts a player-ship task, treats the request like salvage lookup, and fails with `404 Salvage not available`.
- This is now a documented live production mismatch, not just an unimplemented client surface.
- Long runs also exposed one session-auth quirk:
  - after repeated live `/start` calls, fresh sessions sometimes began returning `401`
  - `auth-sync` refreshed the repo `.env`, but the reliable immediate workaround was to pass a newly issued access token inline for the final summary reads

### Port-Code Trade Correction

- Added two new first-class helpers while cleaning up the current live trading surface:
  - `session-nearest-mega-port` to rank known mega-ports by real map distance
  - `session-move-to-sector` to use the exact movement prompt contract and validate arrival
- Used `session-nearest-mega-port` live from sector `3236` and confirmed the nearest known recharge stop is still sector `472`, `9` hops away.
- While trying to keep pushing trading from low warp, found the real bug in the route ranker:
  - it had been comparing buy/sell prices without respecting the port code
  - sector `318` is `SSS`, so it can only SELL Neuro Symbolics to the player, not BUY them from us
  - the earlier `3236 -> 318` NS route looked profitable on price alone but was invalid gameplay
- Reworked the trade-opportunity ranking to respect:
  - port `B`/`S` directionality by commodity slot
  - real port stock at the buy side
  - route-loop safety checks so invalid buy/sell ports are rejected before prompting
- Used the corrected local market view to recover the dirty live hold cleanly:
  - from `318`, ranked valid NS buyers and found `3246` (`BBB`) as the nearest legal sale at `43`
  - used `session-move-to-sector --sector-id 3246` and confirmed arrival headlessly
  - sold the full `30` Neuro Symbolics at `43`, raising credits from `5,689` to `6,979`
- Re-ranked from sector `3246` after the fix and got a coherent live result:
  - best current wealth route: `318 -> 3246` Quantum Foam
  - best current trading-volume route: `318 -> 3246` Neuro Symbolics
  - best current raw-profit route still visible: `3236 -> 907` Neuro Symbolics
- Proved the corrected wealth route live with one full `318 -> 3246` Quantum Foam cycle:
  - profit `+150`
  - credits `6,979 -> 7,129`
  - warp `17 -> 11`
- Pushed exploration again in parallel with the personal-ship cleanup:
  - a fresh probe frontier run raised known sectors from `285` to `295`
  - corporation sectors visited rose from `279` to `289`
  - the probe continued onward and was most recently observed at sector `2419` with its task still active
- Net effect of the correction:
  - exploration rank improved from `39` to `37`
  - trading volume improved from `208,658` to `212,648`
  - wealth estimate improved from `37,839` to `38,229`

### Warp Logistics, Leaderboard Neighbors, And Rescue Work

- Added first-class warp-transfer support in both directions:
  - `session-corp-transfer-warp` was proven live first when `gbheadless Auto Hauler 1` transferred `200` warp to the Kestrel in sector `3246`
  - `session-transfer-warp` was then proven live in the other direction when the Kestrel transferred `100` warp back to the hauler
- That changed the operational model in a useful way:
  - warp is not counted in leaderboard wealth
  - credits and cargo are
  - so moving warp between ships is a real way to extend runs without paying the normal wealth penalty of buying more fuel
- Added a first-class `leaderboard-neighbors` command so the next visible rank targets are explicit instead of inferred from full leaderboard dumps.
- The live gaps right after that addition were:
  - exploration rank `38`, only `6` sectors behind the next visible row
  - trading rank `28`, `22,076` volume behind the next visible row
  - wealth rank `79`, only `32` credits behind the next visible row
- Read the wealth SQL closely enough to confirm the deeper optimization quirk:
  - cargo is scored at a flat `100` credits per unit in the live leaderboard view
  - that means cheap cargo is the best wealth booster, not expensive cargo
  - in practice, the strongest wealth play is to fill holds with the cheapest available commodity rather than the most profitable one
- Added a first-class `session-corp-move-to-sector` helper after live corp-ship moves kept making partial progress but were too opaque when watched as one broad task.
- Used the new helper immediately on the live account:
  - the hauler started in sector `1413` with `110` warp
  - it progressed through sector `3139`
  - then reached sector `2204`
  - and finally stranded there with `0/500` warp instead of reaching the probe in sector `3341`
- That is still useful progress even though the rescue is incomplete:
  - the helper now makes partial corp movement legible
  - the failure mode is no longer ambiguous
  - we can see exactly where the hauler ran out of fuel
- While trying to meet the hauler, repeated `session-move-to-sector --sector-id 2204` calls moved the Kestrel incrementally through live space even when the helper itself timed out waiting for a final `status.snapshot`.
- The Kestrel path was:
  - `3246 -> 3094`
  - `3094 -> 1333`
  - `1333 -> 867`
- That exposed a new client weakness:
  - long player moves can make real progress while the current helper still reports failure
  - the same kind of progressive move wrapper that now exists for corp ships is still needed for the personal ship
- Trading still moved forward during this rescue/logistics phase:
  - used the exact `session-trade-order` sell surface to clear a dirty `30`-unit NS hold at sector `3246`
  - sold at `43` credits per unit for `1,290` credits
  - pushed visible trading volume to `233,228`
  - improved the trading board from rank `29` to rank `28`
- Net live state after this phase:
  - exploration: `309` known sectors, rank `38`
  - trading: rank `28`
  - wealth: rank `79`
  - Kestrel: sector `867`, `7,549` credits, `212` warp
  - hauler: sector `2204`, `0` warp
  - probe: sector `3341`, `0` warp
- Strategic conclusion from this round:
  - exploration is still one good rescue away from the next visible rank
  - trading remains the steadiest board to grind with exact buy/sell orders
  - wealth is the most exploitable board mechanically because cheap cargo converts cash into leaderboard value more efficiently than profitable cargo does

### Mega-Port Reset, Cheap Cargo Wealth, And Fresh Probes

- Reworked `session-move-to-sector` into a segmented mover with status-retry recovery after the old exact mover kept timing out on long live travel while still advancing the ship.
- Used that hardened mover to get the Kestrel from sector `867` back to mega-port sector `1413`.
- Recharged to full there:
  - warp `194 -> 500`
  - credits `7,549 -> 6,937`
- Queried live `ship.definitions` and confirmed the useful reset fact:
  - `Autonomous Probe` costs only `1,000`
  - `Autonomous Light Hauler` costs `5,000`
- Revalidated the wealth-board exploit with a forced refresh instead of trusting stale cached rows:
  - sector `1413` sells `Retro Organics` at `8`
  - a full `30`-hold RO buy cost only `240`
  - visible wealth jumped from rank `79` to rank `71`
  - refreshed visible wealth row moved to `41,797`
- That made the live rule concrete rather than inferred:
  - cheap cargo really is the strongest near-term wealth lever
  - the best wealth move at a good mega-port is often to park the Kestrel with the cheapest full hold available
- Revisited unowned-ship collection immediately after that.
- Fixed the client bug first:
  - `session-collect-unowned-ship` now includes the sector instead of emitting `collect ... in sector`
  - if `--sector-id` is omitted, it derives the current sector from live status
- After that fix, the remaining failure was clearly upstream/live:
  - the bot no longer asked for missing context
  - it still failed on a real in-sector unowned Sparrow Scout in sector `1413`
  - the task summary says it falls back to `salvage_collect` and gets `404 'Salvage not available'`
- So the unowned-ship result is now sharper:
  - one client-side prompt bug is fixed
  - one real live collection-path mismatch still exists
- Changed exploration strategy accordingly:
  - buying fresh probes at a mega-port is a better exploration lever than spending the Kestrel on a long rescue chain
- Bought a new corporation `Autonomous Probe` at sector `1413`.
- The live purchase created:
  - `gbheadless Auto Probe I`
  - ship id `c28f283e-072d-4d63-86cb-ada75ad4ed48`
  - seeded `500` credits on the new probe
- Sent that fresh probe on a `10`-sector frontier task from `1413`.
- The probe task proved the strategy even though the watcher still needs work:
  - known sectors moved `309 -> 313`
  - corporation sectors visited moved `303 -> 307`
  - the probe reached sector `4892`
  - the task was still active when the bounded loop returned
- That tightened the exploration board materially:
  - visible value moved to `313`
  - the next visible row is now only `2` sectors away
- Rebased the trading search from the new `1413` hub:
  - best raw profit from the visible graph: `Quantum Foam` `1413 -> 2891`
  - best trading volume per hop: `Retro Organics` `1413 -> 3124`
- Started a long `session-trade-route-loop` on that one-hop RO route.
- That produced a useful mixed finding:
  - it clearly increased live trading volume from `233,468` to `239,348`
  - it raised personal trades from `239` to `260`
  - it kept the ship trading for real
  - but it did not yield a prompt bounded final result object, so large blind batches are still too opaque to count as a clean unattended surface
- Latest observed live state during that RO grind:
  - Kestrel in sector `3124`
  - `6,037` credits
  - `30` RO on board
  - `431/500` warp
- Strategic conclusion from this round:
  - fresh probes are now the best exploration lever available at a mega-port
  - cheap RO holds are the best short-term wealth lever from `1413`
  - short explicit RO chunks are the right trading tool, but the current large-batch route loop still needs better observability before it should be trusted for long unattended runs

### Wealth Loadout And Fine-Grained Rank Pushes

- Added a first-class `session-wealth-loadout` command so the client can turn
  "cheap cargo is good for wealth" into a bounded reusable surface instead of a
  remembered manual trick.
- Proved it live from sector `3124`, where the Kestrel was already parked:
  - live port state was `SBS`
  - the helper chose `Quantum Foam` automatically as the cheapest legal sell
    at that port
  - it bought `30` units at `23` credits each for `690` total credits
  - task watching stayed clean and ended on a real `task.finish`
- That one bounded command moved the public boards materially:
  - wealth improved from rank `74` to rank `69`
  - trading volume also ticked up from `244,748` to `245,438`
- That is a better wealth surface than the earlier broad statement "buy cheap
  cargo somewhere." It is now explicit, bounded, and keyed to the ship's real
  current location instead of assuming a remembered mega-port.
- Used the now-cheaper exploration target next:
  - before the push, the next visible exploration row was only `1` sector away
  - a single bounded `session-corp-explore-loop` run moved
    `gbheadless Auto Probe I` from `1808` to `2984`
  - known sectors improved `318 -> 319`
  - corporation sectors visited improved `312 -> 313`
  - visible exploration improved from rank `38` to rank `37`
- Strategy shift after those two commands:
  - exploration is still the cheapest board to advance one row at a time
  - `session-wealth-loadout` is now the cleanest way to force a quick wealth
    jump without committing to a long trade cycle
  - trading remains the slowest board to move because it needs larger absolute
    volume gains than the other two

## Personal Impressions

From this headless playthrough, the game is more interesting than a conventional space-trading grind because the interface is part of the game. The strongest idea here is that progress comes from learning how to drive an agent-mediated world, not just from clicking faster through menus.

The parts I like most are the moments where the systems click together: buying into a better ship, forming a corporation, then tasking autonomous probes and seeing real `task.start` and `task.finish` events come back from the live world. That makes the game feel less like a static economy sim and more like a lightweight operations sandbox.

The rough edges are very visible. Some surfaces are elegant when they work, but others are brittle, ambiguous, or route to the wrong backend behavior, as with the current unowned-ship collection mismatch. That said, those edges are also revealing: they make it clear where the game is genuinely systemic and where it is still held together by prompt conventions and hidden assumptions.

The leaderboard split made the midgame much better than the tutorial alone suggested. Having personal trading count separately from corporation exploration forces a real division of labor: the human-run ship becomes the profit engine while the probe becomes the map-expansion tool. That is a clever structure because it makes automation feel like playing the game correctly, not just scripting around it.

The current weakness is operational brittleness rather than game design. Long-lived auth, occasional task failures, and prompt-surface mismatches still need smoothing out before this feels like a truly durable "forever loop" client. But once the three leaderboard categories all became visible from the headless path, the game started to feel less like a guided experiment and more like an open-ended systems game with a real next layer.

The auth fix made a practical difference to how the game feels from the automation side. Before that, a good loop could still degrade into credential babysitting. After it, the headless client started feeling less like a brittle exploit chain and more like a real operator console.

The exact trade-order discovery made the economy feel smarter than the earlier fixed-route grind. Once the bot started interpreting "sell 9 at at least 40" as "go find the best reachable market and do it," the trading layer felt less like rote waypoint replay and more like giving the game a concrete commercial intent.

The route-ranking pass made the game feel more legible. Once the headless client could distinguish "best profit route" from "best trade-volume route," the leaderboard chase stopped feeling like random grinding and started feeling like running a small logistics desk with different KPIs.

The map-backed version sharpened that feeling even more. As soon as shortest-path distance replaced the earlier hop-delta guess, some of the "obvious" routes stopped being optimal, which made the game feel less like memorizing folklore and more like doing real operations work against an imperfect but understandable world model.

Overall impression: the core idea is strong. It feels novel, a little weird in a good way, and substantially more interesting than the average browser game because the player is effectively learning how to operate an in-world organization through language and automation.
