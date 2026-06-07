---
name: analyzer-improvement-check
description: "Use when: validating strategy improvements with live analyzer evidence, comparing baseline vs candidate configs, replaying optimizer artifacts, checking optimizer-vs-analyzer parity, or running postconfigure sweep after quantile updates."
---

# Analyzer Improvement Check

## Principles

- Analyzer validation is required before any promote-or-reject decision.
- Compare baseline and candidate on the same date window, timeframe, exchange, watchlist scope, and capital assumptions.
- If code or config changed after a candidate was first generated, pre-change artifacts are stale; regenerate post-change evidence before comparing.
- Do not run this workflow against a `STOCK_DASHBOARD_TEST_MODE=true` server.
- Treat analyzer/optimizer disagreements as parity issues until metric scope is normalized and explained.

## When to Use

- Stage 6 of [improve-strategy.agent.md](../../agents/improve-strategy.agent.md)
- Any strategy-improvement workflow that needs a fair baseline vs candidate decision
- Cases where optimizer artifacts exist and should be replayed instead of manually reconstructing analyzer payloads
- Cases where `--update-params --quantile-update` was used and confidence-level quality must be checked

## Procedure

### Step 1 — Lock Comparison Context

1. Choose one reachable non-test-mode dev server port and reuse it for the whole validation.
2. Record the shared comparison context: watchlist scope, timeframe, date window, exchange, commission, starting capital, and investment percent.
3. Identify both comparison scopes up front:
   - the targeted acceptance slice used to test the hypothesis
   - the broader comparison context used for the final decision

### Step 2 — Ensure Candidate Freshness

1. If Stage 5 changed strategy config, trade params, optimizer logic, analyzer logic, or signal-generation behavior, regenerate or replay a fresh post-change candidate first.
2. Do not compare a post-change baseline against a pre-change candidate.

### Step 3 — Prefer Artifact Replay

1. Reuse exact persisted artifacts whenever possible:
   - `trade_signal_generation_config.json`
   - persisted signal-config snapshots or ids
   - run-config artifacts
   - optimizer analyzer artifacts as supporting context
2. Use `/api/analyzer/analyze` for strategy-backed requests.
3. Use `/api/analyzer/analyze_raw` or the equivalent rich payload path when the full config shape is needed for parity-correct replay.
4. Avoid hand-rebuilding requests when an exact persisted config already exists.

### Step 4 — Capture Decision Metrics

Record the metrics that matter to the plan thresholds:

- `net_profit_after_commission`
- `completed_pairs`
- `total_trades`
- bad-buy and bad-sell metrics
- exit-action mix
- losing symbols
- max profit or walk-forward metrics when relevant

Reuse repo-native aggregation instead of ad-hoc calculations:

- [debug/compare_optimizer_run_quality.py](../../../debug/compare_optimizer_run_quality.py)
- [src/optimizer/sweep_worker_logic.py](../../../src/optimizer/sweep_worker_logic.py)

### Step 5 — Validate Quantile Levels When Applicable

If the candidate came from `--update-params --quantile-update`, run:

```bash
curl -s -X POST http://localhost:<PORT>/api/optimizer/postconfigure-sweep \
  -H 'Content-Type: application/json' \
  -d '{"run_id": "<RUN_ID>", "watchlist_id": 1}' | python -m json.tool
```

Check `levels.EXTREME`, `levels.STRONGER`, `levels.STRONG`, `levels.REGULAR`, and `levels.WEAK`:

- each level should have meaningful trade counts
- flag any level with zero trades
- flag material profit regression versus baseline
- expect EXTREME to be higher-quality and lower-trade, and WEAK to be broader and higher-trade
- net profit should not degrade as confidence rises without an explained reason

### Step 6 — Resolve Optimizer vs Analyzer Parity

When analyzer output conflicts with optimizer summaries:

1. Check whether optimizer `net_profit_after_commission` is a score-scope average instead of a total.
2. Prefer explicit scope fields such as:
   - `average_net_profit_after_commission`
   - `total_net_profit_after_commission`
   - `net_profit_scope`
3. Do not compare score-scope averages directly against live-analyzer totals.
4. Treat unresolved differences as parity bugs, not promotion evidence.

### Step 7 — Persist Evidence

1. Write a concise analyzer-validation note into the active plan.
2. Keep the underlying evidence in persistent artifacts under `analysis/` or referenced run files.
3. Make the final promote-or-reject stage point back to this evidence explicitly.

## Exit Criteria

- A fresh candidate exists when post-change regeneration was required.
- Baseline and candidate were compared on identical runtime context.
- Quantile levels were checked when applicable.
- Analyzer evidence is persisted and strong enough to support an explicit decision.