---
name: performance-optimization
description: "Use when: investigating or improving slow analyzer, optimizer, datasource, trading, Flask API, Socket.IO, UI, chart, test-suite, or startup behavior; requires measurement before optimization and before/after evidence."
---

# Performance Optimization Skill

## Principles

Measure before optimizing. Performance work without baseline evidence is guessing and often adds complexity in the wrong place.

Optimization workflow:
1. Measure baseline.
2. Identify the bottleneck.
3. Fix the bottleneck with the smallest change.
4. Measure again.
5. Add a guard when regression risk is meaningful.

## When To Use

- Users or tests report slow behavior.
- Analyzer, optimizer, strategy, datasource, API, Socket.IO, chart, or UI changes may affect hot paths.
- A feature handles large ticker lists, long date ranges, repeated calculations, or streaming updates.
- You are adding caching, batching, pagination, concurrency, or memoization.
- You need to compare performance before and after a change.

## What To Measure

### Backend And Data

- API response time and payload size.
- Number of exchange/datasource calls.
- Repeated historical-data fetches.
- Analyzer/optimizer run time and per-symbol/per-timeframe cost.
- Memory growth from large DataFrames or unbounded caches.
- Lock contention or repeated Socket.IO emissions.

### Frontend

- Network waterfall and response payload size.
- Long tasks, layout shifts, and chart rendering time.
- DOM size and repeated rerenders/repaints.
- Text/layout overlap after data loads.
- Console warnings caused by heavy or repeated work.

### Tests

- Slow pytest selectors.
- Playwright shards with repeated server setup or unstable waits.
- Full-suite runtime regressions.

## Procedure

### Step 1 - Capture Baseline

Use the lowest-cost measurement that answers the question:
- Existing test durations.
- Targeted script timing under `debug/` when needed.
- API timing logs.
- Browser network/performance tools.
- Analyzer/optimizer artifacts and replay logs.

Store temporary measurement artifacts under `out/` or `logs/`, not the source tree.

### Step 2 - Locate The Bottleneck

Do not optimize broad areas. Identify the specific expensive operation, for example:
- N repeated data fetches instead of one batched fetch.
- Recomputing indicators for unchanged inputs.
- Unbounded date ranges or ticker lists.
- Large JSON payloads serialized repeatedly.
- DOM updates on every streaming tick.
- Sleep/poll loops or inefficient waits in tests.

### Step 3 - Fix Conservatively

Prefer simple, local changes:
- Add bounds, pagination, or date-range limits.
- Reuse existing caches when validity is clear.
- Batch work at a natural boundary.
- Avoid duplicate computations.
- Move expensive work out of hot loops.
- Reduce payloads to fields the caller uses.

Do not add complex caching or concurrency without clear invalidation and tests.

### Step 4 - Verify Behavior And Performance

Run the same measurement after the change and compare numbers. Also run correctness tests because faster wrong code is not an improvement.

For broad performance-sensitive changes, use `.github/skills/test/SKILL.md` to choose focused and full validation.

## Red Flags

- Optimization with no baseline.
- A cache with unclear invalidation.
- Performance claim without before/after numbers.
- Unbounded list endpoints, date ranges, loops, or stored data.
- Large DataFrames or JSON payloads copied repeatedly.
- Async/concurrency added without understanding shared state.
- Micro-optimizing cold code while hot paths remain unmeasured.

## Exit Criteria

- [ ] Baseline measurement exists.
- [ ] The actual bottleneck is identified.
- [ ] The fix targets that bottleneck and preserves behavior.
- [ ] Before/after measurements show the result.
- [ ] Focused correctness tests pass.
- [ ] Any new cache, batch, or bound has a documented validity rule.