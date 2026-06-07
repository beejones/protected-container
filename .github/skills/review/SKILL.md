---
name: review
description: "Use when: invoking /review, reviewing code before merge, evaluating agent or human changes, checking correctness, typing, JSON safety, strategy contracts, docs, tests, security, performance, or deciding whether a change is ready for PR/merge."
---

# Review Skill

## Principles

Review is a quality gate, not a rubber stamp. Lead with concrete findings, ordered by severity, and ground every issue in observable code, behavior, or missing evidence.

The approval standard is practical: approve changes that improve the codebase and satisfy repo rules, even if they are not exactly how you would have written them. Block correctness, safety, typing, contract, or verification problems.

## When To Use

- The user invokes `/review`.
- A change is ready for merge or PR reporting.
- Another agent, model, or human produced code that needs scrutiny.
- A feature, bug fix, refactor, or strategy change has completed implementation.
- The diff touches shared contracts, user workflows, auth, data sources, analyzer/optimizer/trading logic, or UI behavior.

## Review Axes

### Correctness

- Does the change satisfy the request or planning file?
- Are edge cases handled: empty inputs, missing data, NaN/inf values, network/API failures, partial payloads, and date/time boundaries?
- Do analyzer, optimizer, trading, and strategy changes preserve documented contracts?
- Are error paths intentional and graceful?
- Does the verification evidence actually cover the changed behavior?

### Repo Conventions

- Python changes follow `.github/skills/typed-code-generation/SKILL.md`.
- Raw `dict`, `object`, `Any`, or optional-required values do not leak into core logic.
- API JSON responses sanitize `NaN` and infinity to `None` before `jsonify`.
- Data-source access goes through `DataManager` unless there is a clear reason.
- Signal generation uses `collect_signal_generation_request(...)` and `generate_signals_with_strategies(...)` where applicable.
- Strategy JSON does not put UI-owned values such as `timeframe` or `min_confidence` in strategy files.

### Architecture

- Boundaries are clean: APIs normalize raw input, internal code receives typed values.
- Existing helpers in `src/common/` or the target module are reused before creating new abstractions.
- New abstractions earn their complexity.
- Related docs in `docs/<module>/` are updated and not duplicated.

### Security

- Secrets are not read, logged, committed, or surfaced.
- Auth and access-key behavior remains intentional.
- External data, browser content, config, request JSON, and exchange responses are treated as untrusted at boundaries.
- Error responses do not expose internal stack traces or sensitive values.

### Performance

- No unbounded loops, payloads, caches, or list endpoints are introduced.
- Analyzer/optimizer/data-source hot paths avoid repeated expensive work.
- UI changes do not introduce obvious layout thrash, excessive DOM updates, or heavyweight assets.
- Performance claims have measurements.

## Procedure

### Step 1 - Understand Scope

Read the user request, planning file, or PR context first. Identify intended behavior, non-goals, touched modules, and expected validation.

### Step 2 - Review Tests First

Check whether tests or replay evidence describe the behavior:
- Focused pytest coverage for backend logic.
- Playwright coverage for UI behavior.
- Analyzer/optimizer evidence for strategy-sensitive changes.
- Full `scripts/run_tests.py` when broad workflows or shared contracts changed.

Tests should assert outcomes, not implementation details. Do not accept skipped or weakened tests without explanation.

### Step 3 - Inspect The Implementation

Review changed files through the axes above. For large diffs, group findings by severity and affected area.

### Step 4 - Verify Verification

Record what validation ran, what passed, and what did not run. If evidence is missing, call that out as a risk or required change depending on blast radius.

### Step 5 - Report Findings

Use this order:
1. Findings first, ordered by severity.
2. Open questions or assumptions.
3. Brief change summary only after findings.
4. Verification status.

Finding format:
- Severity: Critical, High, Medium, Low, or Nit.
- Location: clickable file link when available.
- Problem: what can go wrong.
- Evidence: why the code or missing test proves the issue.
- Fix direction: concise recommendation.

If there are no findings, say that clearly and still mention residual risk or missing test coverage.

## Red Flags

- "LGTM" without evidence.
- Tests pass but the change violates typing, API, auth, or strategy contracts.
- Bug fixes without a regression test that failed first.
- UI changes without Playwright or manual browser verification.
- Strategy changes without analyzer/optimizer evidence.
- Large mixed diffs combining feature work, refactor, docs, and unrelated cleanup.
- Review comments framed as personal preference rather than code health.

## Exit Criteria

- [ ] Findings are listed first and ordered by severity.
- [ ] Correctness, repo conventions, architecture, security, and performance were considered.
- [ ] Verification evidence is summarized honestly.
- [ ] Required fixes are distinguished from optional suggestions.
- [ ] No issue relies on speculation when code or tests can prove it.