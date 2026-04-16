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

- `session-probe-frontier-loop` is now the highest-confidence compounding
  surface.
- The probe-local branch chain `2015 -> 790 -> 2896 -> 3404 -> 3560 -> 3870`
  is real and has now delivered five consecutive successful exploration pushes.
- Latest strong exploration state:
  - exploration `408`, visible rank `28`
  - next visible row is only `3` sectors above
  - probe ended the last successful run at sector `3870`
- Latest strong trading state:
  - trading `290872`, visible rank `27`
  - player ship is clean and liquid at sector `256`
- Latest wealth state is weaker after liquidation:
  - wealth `44409`, visible rank `66`
  - do not assume `session-wealth-loadout` is reliable until it is re-proven

## What To Do Next

1. Keep running probe-led exploration while the next visible exploration row
   remains cheaper than the next trading or wealth row.
   Use `session-probe-fleet-loop` whenever there is more than one eligible
   probe; otherwise keep using `session-probe-frontier-loop`.
2. Force-refresh leaderboard state after meaningful exploration jumps.
3. Only spend player-ship time on short exact trade batches if:
   - exploration stalls temporarily, or
   - a clearly superior legal route is available from the current position.
4. Re-verify or replace the current wealth-padding helper before using wealth
   as a target again.
