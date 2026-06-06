---
name: performance-optimization
description: "Use when: investigating or improving slow deploys, Docker builds, validation, env schema parsing, CI, Azure/Ubuntu operations, storage-manager behavior, browser flows, or test-suite runtime; requires baseline and before/after evidence."
---

# Performance Optimization Skill

## Principles

Measure before optimizing. Deployment performance work without a baseline is guessing and can add risky complexity.

## When To Use

- Build, deploy, validation, Compose rendering, env parsing, GitHub Actions sync, Azure/Ubuntu operations, browser flows, or tests become slow.
- A change may affect large env schemas, Compose files, generated YAML, Docker builds, remote calls, or CI time.

## Procedure

1. Define the symptom and target surface.
2. Capture a baseline with logs, test duration, command timing, CI output, browser trace, or deploy artifact.
3. Identify the specific bottleneck.
4. Fix the smallest proven bottleneck: reduce repeated work, bound loops, cache with clear invalidation, batch provider calls, or reduce payloads.
5. Rerun the same measurement and compare.
6. Run correctness validation.

## Red Flags

- Optimization starts without baseline data.
- Cache has no invalidation story.
- Provider/API call changes lack retry/failure consideration.
- Faster code changes deploy behavior or error handling silently.
- Performance claims lack before/after numbers.

## Exit Criteria

- [ ] Baseline measurement exists.
- [ ] The bottleneck is identified.
- [ ] The fix targets that bottleneck and preserves behavior.
- [ ] Before/after numbers show the effect.
- [ ] Correctness tests still pass.