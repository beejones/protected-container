---
name: strategy-promotion-adoption
description: "Use when: promoting or rejecting improved strategy params after analyzer validation, writing persistent decision reports, backing up and updating trade strategy and trade params JSON, or applying optimizer artifacts safely."
---

# Strategy Promotion / Adoption

## Principles

- No strategy-improvement workflow is complete without a persistent decision artifact under `analysis/`.
- `out/tmp/` is scratch only; rejection or promotion reports must be durable.
- Rejection leaves production strategy and trade params unchanged.
- Promotion requires `.bak` backups before any writes.
- Do not modify `exit_config` unless the plan explicitly authorizes it.
- Read and preserve optimizer artifacts before `python scripts/run_tests.py`, because the test suite cleans `out/optimizers/`.

## When to Use

- Stage 7 of [improve-strategy.agent.md](../../agents/improve-strategy.agent.md)
- Any workflow that needs to convert validated candidate results into an explicit promote-or-reject outcome
- Any task applying optimizer artifacts back into `config/trade_strategies/` or `config/trade_params/`

## Procedure

### Step 1 — Make The Comparator Explicit

1. Compare the best corrected candidate against the original diagnostic baseline.
2. Check the plan thresholds, targeted-slice acceptance criteria, broader watchlist criteria, and analyzer results.
3. Decide whether the evidence supports promotion or rejection.

### Step 2 — Write The Persistent Decision Report

1. Create `analysis/strategy_improvement_decision_<strategy_id>_<run_id>.md`.
2. Title it explicitly as `Rejection Report` or `Promotion Report` / `Adoption Report`.
3. Include all of the following:
   - scope and comparator
   - what changed before the rerun
   - analyzer validation summary
   - best candidate summary
   - side-by-side comparison versus baseline
   - root-cause summary
   - explicit decision
   - next-step recommendation
4. Do not leave the only final report in `out/tmp/`.

### Step 3 — Rejection Path

1. Keep current production strategy and params unchanged.
2. Update the plan with the rejection reason and a link to the persistent report.
3. Leave follow-up recommendations narrow and concrete.

### Step 4 — Promotion Path

1. Back up `config/trade_strategies/<strategy_id>.json` to `.bak` before modifying it.
2. Update only plan-approved fields, typically `signal_config.indicator_params` and related approved config.
3. If the run produced `artifacts/trade_params__*.json`, back up and update the matching `config/trade_params/<name>.json`.
4. If the artifact does not already contain per-confidence-level params, scale them with `scale_params_across_levels()`.
5. Do not modify `exit_config` unless the plan explicitly authorizes it.
6. Summarize which files were modified.

### Step 5 — Final Verification And Plan Update

1. Read or copy any optimizer artifacts you still need before testing.
2. Run the full suite:

```bash
source .venv/bin/activate && python scripts/run_tests.py
```

3. Report pass/fail count and whether failures are expected from param changes or are true regressions.
4. Update the active plan with the decision summary and a link to the persistent report.

## Exit Criteria

- A persistent decision report exists in `analysis/`.
- Strategy files were either safely updated with backups or left untouched on rejection.
- The plan links to the final decision report.
- Final verification ran after the needed optimizer artifacts were consumed.