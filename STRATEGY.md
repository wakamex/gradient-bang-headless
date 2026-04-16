# Live Strategy

This file tracks only the current live strategy for maximizing long-term return
on the visible player leaderboards: `exploration`, `trading`, and `wealth`.

## Goal

Restore compounding exploration capacity first, then convert that position into
trading and wealth gains.

## Priority Order

1. Rescue and restore exploration assets
2. Resume probe-led frontier expansion
3. Trading throughput
4. Wealth padding

## Current Live Facts

- Player ship `gbheadless Kestrel` is stranded at port sector `4145` with
  `0/500` warp and `11,469` credits.
- Surviving probe `gbheadless Auto Probe 1` remains in sector `3341` with
  `3/500` warp.
- `gbheadless Auto Hauler 1` is stranded in sector `2204` with `0/500` warp.
- `gbheadless Auto Probe I` was destroyed in sector `1469` after a blind corp
  move routed through a hostile garrison sector.
- The next validated frontier from the probe pocket is `3341 -> ... -> 4438`,
  distance `13`.
- Current visible ranks:
  - exploration `421`, rank `28`
  - trading `291,772`, rank `27`
  - wealth `42,569`, rank `64`

## Strategy

### 1. Rescue Still Comes First

- Use `session-corp-move-to-sector` for corporation logistics only through the
  new safe router that avoids known foreign garrison sectors.
- Use `session-send-message` for rescue coordination:
  - broadcast when the goal is general warp assistance
  - direct message known helpers when a targeted ask is higher probability
- Keep the probe parked in sector `3341` until outside warp arrives.
- Do not spend newly received rescue warp on anything except reopening
  exploration.

Why:

- Exploration is still the best long-term board lever, but it is currently fuel
  constrained.
- Rescue messaging is a regular-player surface that has already worked live for
  other players and is now proven in this client.
- The player ship is now at `0` warp, so outside assistance is the cleanest way
  back to the frontier.

### 2. Use The Local Trade Pocket Only As A Secondary Fallback

- The best proved stranded-pocket route is:
  - `3328 -> 4145` on `Neuro Symbolics`
  - `4145 -> 3328` on `Quantum Foam`
- Run that route only when there is enough warp to finish the intended unloads
  cleanly, or when rescue has clearly stalled.
- Prefer exact deterministic surfaces:
  `session-load-cargo -> session-move-to-sector -> session-liquidate-cargo`
  or a bounded `session-shuttle-loop`.

Why:

- That pocket raises trading and wealth without needing a mega-port.
- It is useful, but it is still subordinate to exploration recovery.

### 3. Preserve Value Before Honoring Stop Thresholds

- Keep using the safe `session-corp-move-to-sector` router for corp movement.
- Treat low-warp stop conditions as movement guards, not reasons to skip an
  in-place unload at a valid sell port.
- Prefer surfaces that leave the ship in a clean cash state after partial
  progress instead of stranded with cargo.

Why:

- The latest live shuttle run showed that a loop can make real progress and
  still lose value if it stops at the wrong boundary.
- Fixing that class of issue is higher ROI than adding more brittle action
  surfaces.

### 4. Reopen Exploration As Soon As Fuel Lands

- The first use of new warp should be to push the surviving probe toward the
  validated `4438` branch.
- Keep using `session-frontier-candidates` before each redeploy.
- Once the probe can reach the branch, switch back to
  `session-probe-frontier-loop` as the default exploration engine.
- Use `session-probe-fleet-loop` again only after another probe is active.

Why:

- Exploration directly raises the strongest compounding board.
- More known sectors also improve future route discovery for trading.

### 5. Wealth Stays Incidental

- Do not chase cargo-padding wealth bumps while stranded.
- Let wealth rise as a consequence of resumed exploration and trading.

Why:

- Wealth is the least compounding board in the current live state.

## Next Moves

1. Keep monitoring for rescue responses, especially from the updated direct ask
   to `NillaWafer`.
2. If rescue arrives, transfer warp into the surviving probe first.
3. Spend the next meaningful warp on the validated `4438` frontier branch.
4. If rescue stalls but local warp becomes available, use one bounded
   `3328 <-> 4145` exact trade cycle before re-evaluating.
