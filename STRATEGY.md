# Live Strategy

This file tracks only the current live strategy for maximizing long-term return
on the visible player leaderboards: `exploration`, `trading`, and `wealth`.

## Goal

Maximize compounding exploration throughput first, then use the resulting map
and fleet position to improve trading and wealth.

## Current Live Facts

- Personal ship `gbheadless Kestrel` is back at mega-port sector `1413` with
  `9,469` credits, empty cargo, and `89/500` warp.
- Corporation fleet:
  - `gbheadless Auto Probe 1`: sector `4572`, `176/500` warp
  - `gbheadless Auto Probe 2`: sector `3916`, `473/500` warp
  - `gbheadless Auto Probe 3`: sector `1333`, `497/500` warp
  - `gbheadless Auto Hauler 1`: sector `2204`, `0/500` warp
- Current visible leaderboard state observed on April 16, 2026:
  - exploration: `444` known sectors, visible rank `29`
  - trading: `293,332`, visible rank `27`
  - wealth: `42,569`, visible rank `70`
- `session-purchase-corp-ship` is now proven for repeated single-probe buys at
  sector `1413`.
- `session-probe-frontier-loop` is now proven again on a fresh staged probe:
  `Auto Probe 2` started from sector `2548`, pushed toward target sector
  `3494`, ended in sector `3916`, and added `+13` known sectors.

## Priority Order

1. Probe-driven exploration throughput
2. Cheap probe fleet growth
3. Safe logistics and recharge support
4. Trading only when it funds more exploration capacity
5. Wealth only as a side effect

## Strategy

### 1. Exploration Is The Main Engine

- Use `session-frontier-candidates` from each active probe pocket, not from the
  Kestrel, before spending fresh warp.
- Prefer high-warp probes on validated frontier branches.
- Keep using `session-probe-frontier-loop` now that it passes explicit branch
  targets into the corp task prompt.
- Use `session-probe-fleet-loop` only when at least two probes have meaningful
  warp and distinct frontier pockets.

Why:

- Exploration still compounds hardest. It raises the exploration board
  directly and improves future route discovery for trading.
- The latest live proof showed the missing lever was not more fuel, but more
  specific branch guidance for fresh probes.

### 2. Buy More Probes Before Grinding More Trade

- While parked at sector `1413`, treat spare Kestrel credits as exploration
  capital first.
- Use `session-purchase-corp-ship` one probe at a time rather than batch buys.
- Do not rely on corporation bank assumptions; corp ship purchases must be paid
  from current personal-ship credits on hand.

Why:

- A cheap probe adds parallel exploration capacity and also lifts wealth.
- Another short trade loop does not compound as hard as another successful
  exploration worker.

### 3. Use Logistics As Support, Not As The Goal

- Keep the Kestrel at a mega-port unless there is a specific logistics reason
  to move it.
- Use `session-corp-move-to-sector` for safe corp repositioning.
- Use `session-transfer-warp --wait-for-finish` whenever refueling another ship
  matters.
- Use `session-send-message` and `session-chat-watch` only when a real rescue
  or coordination ask is needed.

Why:

- Rescue and routing are important, but they are supporting systems now, not
  the main source of leaderboard growth.

### 4. Trading Is Secondary Until Exploration Stalls

- Do not spend Kestrel warp on routine trade loops while three live probes are
  available.
- Only trade when it clearly funds another probe, another recharge cycle, or a
  necessary reposition.
- Prefer exact deterministic surfaces over open-ended trade chat.

Why:

- Trading is visible already and not the best marginal use of time from the
  current account state.
- The map and fleet are finally in a position where exploration has better
  long-term ROI.

### 5. Wealth Is Not A Primary Objective

- Let wealth rise from ship purchases and successful exploration support.
- Do not chase cargo-padding or temporary wealth snapshots unless the strategy
  changes materially.

Why:

- Wealth is the least compounding board in the current live state.

## Next Moves

1. Push `Auto Probe 3` from the `1333` pocket onto its first validated frontier
   branch.
2. Re-run `session-probe-fleet-loop` once at least two probes have distinct
   actionable branches.
3. Spend the next Kestrel credits on another probe before resuming routine
   trading, unless live probe coverage clearly saturates.
