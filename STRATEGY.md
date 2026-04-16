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

- Player ship `gbheadless Kestrel` is parked in sector `3341` with `6/500`
  warp and `10,809` credits.
- Surviving probe `gbheadless Auto Probe 1` is also in sector `3341` with
  `3/500` warp.
- `gbheadless Auto Hauler 1` is stranded in sector `2204` with `0/500` warp.
- `gbheadless Auto Probe I` was destroyed in sector `1469` after a blind corp
  move routed through a hostile garrison sector.
- The next validated frontier from the current rescue sector is
  `3341 -> ... -> 4438`, distance `13`.
- Current visible ranks:
  - exploration `421`, rank `28`
  - trading `290,872`, rank `27`
  - wealth `41,909`, rank `68`

## Strategy

### 1. Rescue Before Grinding

- Do not spend the Kestrel's last `6` warp on local trade loops right now.
- Use `session-corp-move-to-sector` for corporation logistics only through the
  new safe router that avoids known foreign garrison sectors.
- Use `session-send-message` for rescue coordination:
  - broadcast when the goal is general warp assistance
  - direct message known helpers when a targeted ask is higher probability
- Keep both the Kestrel and the surviving probe parked together in sector
  `3341` until outside warp arrives or a clearly better local plan appears.

Why:

- Exploration is still the best long-term board lever, but it is currently fuel
  constrained.
- Rescue messaging is a regular-player surface that has already worked live for
  other players and is now proven in this client.
- Preserving the remaining warp is worth more than a tiny local trade gain.

### 2. Reopen Exploration As Soon As Fuel Lands

- The first use of new warp should be to push the surviving probe toward the
  validated `4438` branch.
- Keep using `session-frontier-candidates` before each redeploy.
- Once the probe can reach the branch, switch back to
  `session-probe-frontier-loop` as the default exploration engine.
- Use `session-probe-fleet-loop` again only after another probe is active.

Why:

- Exploration directly raises the strongest compounding board.
- More known sectors also improve future route discovery for trading.

### 3. Trading Only As A Secondary Fallback

- If rescue stalls and no exploration branch is reachable, use short exact
  trade batches only if they preserve enough warp to resume rescue work.
- Keep the reliable contract:
  `session-load-cargo -> session-move-to-sector -> session-liquidate-cargo`.
- Prefer legal, short, stock-aware routes over raw margin stories.

Why:

- Trading is useful, but right now it competes directly with the fuel needed to
  restart exploration.

### 4. Wealth Stays Incidental

- Do not chase cargo-padding wealth bumps while stranded.
- Let wealth rise as a consequence of resumed exploration and trading.

Why:

- Wealth is the least compounding board in the current live state.

## Next Moves

1. Keep monitoring for rescue responses through chat history.
2. If rescue arrives, transfer warp into the surviving probe first.
3. Spend the next meaningful warp on the validated `4438` frontier branch.
4. Only fall back to local trade if rescue remains silent and the ship would
   otherwise sit idle too long.
