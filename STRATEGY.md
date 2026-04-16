# Live Strategy

This file tracks only the current live strategy for maximizing long-term return
on the three visible player leaderboards: `exploration`, `trading`, and
`wealth`.

## Goal

Build compounding engines first, then use short exact actions to convert that
position into leaderboard gains.

## Priority Order

1. Exploration infrastructure
2. Trading throughput
3. Wealth padding

## Current Strategy

### 1. Exploration First

- The best long-term ROI is corporation-probe exploration.
- Use `session-probe-frontier-loop` as the default exploration surface.
- Use `session-probe-fleet-loop` whenever more than one probe is eligible.
- Search from the probe's current sector first, not the player's sector.
- Only treat a frontier as real if the map read shows actionable local
  frontier, not just a dangling remembered stub.
- Buy fresh probes when that is cheaper than rescuing dead or stranded hulls.

Why:

- Exploration raises the exploration board directly.
- Exploration also improves the trading board indirectly by discovering new
  ports and new legal routes.
- It is the cleanest compounding loop we currently have.

### 2. Trading Second

- Use exact, bounded trade actions instead of vague bot instructions.
- Prefer short legal routes with clear port-code directionality and known stock.
- Treat `session-load-cargo -> session-move-to-sector -> session-liquidate-cargo`
  as the reliable trading contract.
- Use `session-trade-opportunities` only as a ranking input, not as proof that a
  route is durable enough for unattended looping.

Why:

- Trading is personal-only, so it needs direct player-ship time.
- Volume per minute matters more than raw one-trip profit.
- Exact orders keep the ship from getting stranded in half-completed loops.

### 3. Wealth Third

- Treat wealth as a checkpoint metric, not the primary optimizer.
- Only use wealth-padding helpers when the current live state proves they still
  work on the current port and inventory.
- Prefer durable asset growth and profitable exploration/trading over temporary
  wealth-board cosmetics.

Why:

- Wealth can move up and down sharply when cargo is liquidated.
- The easiest wealth boosts are often temporary and do not compound.

## Current Live Conclusions

- `session-probe-frontier-loop` and `session-probe-fleet-loop` are now the
  highest-confidence compounding surfaces.
- The best recent gain came from rescuing a stranded probe, not from another
  trade loop:
  - moved the Kestrel to sector `3341`
  - transferred `20` warp into `gbheadless Auto Probe 1`
  - immediately converted that rescue into a live `+8` exploration gain
- Latest strong exploration state:
  - exploration `417`, visible rank `26`
  - rescued probe ended its useful branch at sector `4356` with `4` warp
  - high-warp probe redeployed to sector `4393` with `300` warp
- Latest trading state:
  - trading `290872`, visible rank `27`
  - no change this pass, which is acceptable because exploration produced the
    higher-return gain
- Latest wealth state:
  - wealth `43409`, visible rank `67`
  - do not spend player-ship time on wealth padding until exploration stalls

## What To Do Next

1. Keep the two-probe exploration posture alive.
   - use `session-probe-fleet-loop` when both probes have usable warp
   - rescue or recharge corp probes before buying more player-side volume
2. Use `session-frontier-candidates` before spending the high-warp probe.
   - do not trust `no_actionable_frontier` blindly if the direct candidate scan
     still shows adjacent unvisited targets
3. Treat player transfer/recharge prompts as finish-waited tasks.
   - if the session closes early, the bot can cancel the transfer task
   - for now, run transfer helpers with `--wait-for-finish`
4. Only return to trading when:
   - both active probes are dry or locally exhausted, or
   - a short exact route offers a clearly cheaper next board gain than
     exploration
