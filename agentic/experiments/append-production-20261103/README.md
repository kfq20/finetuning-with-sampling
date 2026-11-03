# Append production — 2026-11-03

Each item is an existing append requirement plus its published predecessor file state. Legacy and Foundry sources are identity-deduplicated. Missing or inconsistent states remain explicit source holds. Never substitute the expert's successful successor state for the starting state.

The production protocol is: restore/check inputs → initial-state negative and legal-positive controls → reuse a matching native Terminus expert or run DeepSeek Flash with Terminus → full observable successful expert reference for Qwen generation → eight candidates per native command block → rank with Qwen mean candidate-token logprob under the reference-free public prefix → execute only the selected command batch → actual tool observation → repeat → two isolated final grading restores → assistant-only SFT export.

There is no intermediate verifier selection, environment rewind, whole-episode automatic retry, or default global model budget/concurrency ceiling. Existing source-domain queues run independently. Invalid/missing captures, incomplete native completion, scoring transport exhaustion, and task-adapter errors are holds, never normal model zeros. Completed source expert/method attempts are reused rather than replayed.

Only transient **zero-generation** score POSTs may retry (at most three transport attempts), retaining each request/response/error. Candidate generation and expert episodes do not automatically retry. Authentication/policy/quota errors do not score-retry. The full input logprob range is retained; the unvalidated suffix-range optimization is not selected.

A successful private-reference generation is not automatically training-ready. Export requires both fresh grades equal one, no private-path probing, native action/template/mask validity, and no explicit attribution to a removed expert reference. Raw successful trajectories held for reference attribution are preserved and not relabeled clean SFT.

## Selected deployment

MindLab research root: `/vePFS-Mindverse/user/intern/fanqi/tb4-research/projection-agent-20261102`

- Frozen runtime: `source-production-v4`, commit `e10b714`.
- Read-only source preparation receipt: `data/production-discovery-v3-launch.json`.
- Source registry: `data/production-inputs-v3/plan.json`; final `summary.json` seals its hash.
- Single production coordinator receipt: `data/append-production-v1-launch.json`.
- Outputs: `data/append-production-v1/units/<identity>/{controls,teacher,student}`.
- Per-unit progress: `status.json`. Student success exports: `student/train.jsonl` bound by `student/receipt.json`.
- Coordinator uses exact copied specifications in `data/append-production-v1/specs/` while source discovery publishes additional independently sealed units. Final discovery summary binds the final manifest.

Credentials and original model reasoning stay private. No source experiment, original receipt, grader, or failed-attempt evidence is edited.

## Validation

99 local unit checks (six SDK-dependent skips) and 99 MindLab checks (two skips) passed. Full-range streamed scoring calibration used cached proposals only: short input, an eight-candidate long input pool, and two previously interrupted candidates. It retained the same winner and validated target token IDs/coverage. One HTTP 499 required a second zero-generation score POST; all original failed evidence remains.

Source counts, expert successes and actual SFT release counts are dynamic; use the registry and per-unit receipts rather than this document as a live counter.
