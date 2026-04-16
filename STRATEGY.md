# Strategy

This file is the canonical record of the current high-level strategy for the
Gradient Bang headless client and the live account it is driving.

It exists to answer a different question than `HEADLESS_PLAN.md` or
`NARRATIVE.md`:

- `HEADLESS_PLAN.md` tracks feature work, capability coverage, and blockers.
- `NARRATIVE.md` tracks what actually happened in the live game.
- `STRATEGY.md` explains what to optimize for next, why, and what to stop
  spending time on.

## Goal

Maximize long-term account growth and automation value for a normal live player,
not just the next visible leaderboard bump.

That means preferring durable compounding engines over quick wins.

## Core Pivot

The client should optimize for systems that increase future options and future
throughput automatically, rather than for one-off leaderboard gains.

Current priority order:

1. exploration infrastructure
2. personal trading throughput
3. wealth realization and board padding

Why this order:

- exploration compounds twice: it raises the exploration board directly and
  discovers more ports and routes for future trading
- trading is personal-only and volume-based, so the real lever is repeatable
  legal throughput, not isolated profit spikes
- wealth is the easiest leaderboard to pad temporarily, so it should be treated
  as a checkpoint metric, not the main optimizer

## What To Optimize For

### Exploration As The Primary Compounding Engine

Exploration has the highest long-term ROI because it expands the reachable
market graph and improves future route quality.

Implications:

- build frontier selection instead of reusing stale remembered frontiers
- validate dangling map stubs before treating them as real frontier, because
  some are only off-window known sectors
- score sectors by unexplored adjacency and travel cost
- use corporation probes as the main exploration tool
- buy fresh probes when that is cheaper than rescue chains

### Trading As A Throughput Engine

Trading should be optimized for sustainable volume over time, not just raw
profit per trip.

Primary ranking factors:

- legal route validity under port `B`/`S` directionality
- volume per minute
- stock depth
- hop cost and warp cost
- recovery cost when the ship ends dirty or stranded

Implications:

- maintain a small portfolio of good routes instead of assuming one route stays
  best forever
- prefer exact move/buy/sell sequences over vague freeform prompts
- treat live stock as a first-class route constraint

### Wealth As A Secondary Snapshot Metric

Wealth is still useful, but it should mostly rise as a side effect of better
trading and better assets.

Implications:

- prioritize realized capital growth and productive assets over paper wealth
- use cargo-padding helpers only when intentionally forcing a leaderboard check
- do not over-invest in short-term wealth-only maneuvers that do not improve
  future exploration or trading capacity

## What To Deprioritize

These are lower-ROI uses of time unless they unlock a repeatable surface:

- one-row wealth pushes
- remembered frontier resets without validating that the frontier is still live
- one-off rare actions that do not improve the main loops
- raw profit-per-trip in isolation
- long unattended loops that can advance state but do not return a clean,
  inspectable result

## Current Strategic Bet

The current best long-term bet is:

1. keep turning exploration into a scored, validated, repeatable probe workflow
2. keep the personal ship on short, legal, exact trading cycles that fund the
   next multiplier
3. use wealth-padding only when we want a board snapshot or need to preserve a
   visible position

Current live implication:

- the local `3883` probe pocket looks saturated after stub validation
- the next exploration pushes should come from validated branches like the
  `4790 -> 4407` line, not from raw local dangling stubs

This means the client should move away from “what gets the next row right now?”
and toward “what creates the strongest compounding loop over the next several
hours of play?”

## Proven High-ROI Surface

### `session-frontier-candidates`

Purpose:

- rank local frontier anchors from the session map
- validate dangling stub sectors by probing whether they are actually
  centerable

Why it matters:

- it demotes false frontiers caused by truncated local map windows
- it turns exploration target selection into a repeatable live signal instead
  of a remembered anecdote

## Highest-ROI Client Surfaces To Build Next

These are the next headless surfaces with the best expected strategic value:

### `session-probe-frontier-loop`

Purpose:

- choose the best frontier candidate
- move a probe there
- run a bounded exploration task
- re-score and repeat

Why it matters:

- it converts validated frontier selection into a full compounding loop instead
  of a manual reset ritual

### `session-frontier-atlas`

Purpose:

- merge validated frontier results across multiple map centers instead of
  relying on one local region at a time

Why it matters:

- a single local map window can still miss better branches elsewhere in the
  discovered graph

### `session-trade-portfolio`

Purpose:

- maintain the top legal routes by throughput, profit, and stock resilience

Why it matters:

- it prevents overfitting to one route that may degrade or stock out

### `session-capital-plan`

Purpose:

- track distance to the next meaningful personal ship upgrade or fleet
  multiplier

Why it matters:

- it turns “earn more” into an explicit capital-allocation policy

## Current Operating Rules

When choosing what to do next:

1. prefer work that improves future decision quality or route quality
2. prefer reusable first-class commands over ad hoc prompt scripts
3. prefer exploration and trading capacity upgrades over wealth-only padding
4. only use local-only work if it reduces risk for the live player path
5. treat unvalidated dangling stubs as heuristics, not as final exploration
   targets
6. when a durable surface is discovered, write it into the client before
   leaning on it further

## Update Rules

Keep this file updated whenever one of these changes:

- the best long-term leaderboard strategy changes
- a new durable compounding surface is proven
- a previously good route or frontier heuristic degrades
- the next meaningful capital target changes
- a quick-win tactic is intentionally demoted in favor of a stronger long-term
  loop

When updating this file:

- prefer changes to priorities and rationale, not play-by-play logs
- keep specific live outcomes in `NARRATIVE.md`
- keep feature inventory and blockers in `HEADLESS_PLAN.md`
