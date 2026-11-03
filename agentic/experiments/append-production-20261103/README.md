# Append production — 2026-11-03

Each item is an existing append requirement plus its published predecessor file state. Legacy and Foundry sources are identity-deduplicated. Missing or inconsistent states remain explicit source holds. Never substitute the expert's successful successor state for the starting state.

The production protocol is: restore/check inputs → initial-state negative and legal-positive controls → reuse a matching native Terminus expert or run DeepSeek Flash with Terminus → full observable successful expert reference for Qwen generation → eight candidates per native command block → rank with Qwen mean candidate-token logprob under the reference-free public prefix → execute only the selected command batch → actual tool observation → repeat → two isolated final grading restores → assistant-only SFT export.

There is no intermediate verifier selection, environment rewind, whole-episode automatic retry, or default global model budget/concurrency ceiling. Existing source-domain queues run independently. Invalid/missing captures, incomplete native completion, scoring transport exhaustion, and task-adapter errors are holds, never normal model zeros. Completed source expert/method attempts are reused rather than replayed.

Only transient **zero-generation** score POSTs may retry (at most three transport attempts), retaining each request/response/error. Candidate generation and expert episodes do not automatically retry. Authentication/policy/quota errors do not score-retry. The full input logprob range is retained; the unvalidated suffix-range optimization is not selected.

A successful private-reference generation is not automatically training-ready. Export requires both fresh grades equal one, no private-path probing, native action/template/mask validity, and no explicit attribution to a removed expert reference. Raw successful trajectories held for reference attribution are preserved and not relabeled clean SFT.

## Selected deployment

MindLab research root: `/vePFS-Mindverse/user/intern/fanqi/tb4-research/projection-agent-20261102`

- Active selection: `PRODUCTION_SELECTION.json` (exact run/plan/source bindings).
- Legacy runtime: `source-production-v5`, commit `0608f9f`; run `data/append-production-v2`, original plan `data/production-inputs-v4/plan.json` (140 distinct units).
- Foundry supplement: `source-production-v6`, commit `730d58a`; run `data/append-production-foundry-v1`, plan `data/production-foundry-supplement-v1/plan.json` (91 units disjoint from legacy).
- Foundry adapter repair: `source-production-v7`, commit `c441cf9`; run `data/append-production-foundry-repair-v1`, plan `data/foundry-template-adapter-repair-v1/plan.json`. These 77 units had **zero model requests** and were held solely because the original adapter omitted Harbor's computed template alias. The repair records old-to-new runtime identities and never repeats a paid expert/student attempt.
- Explicit/custom-adapter repair: `source-production-v10`, commit `163fb8f`; run `data/append-production-foundry-explicit-v2`, plan `data/foundry-explicit-adapter-repair-v2/plan.json`. The current source recognizes `template_name`, `template_alias`, `pinned_template`, `existing_template`, and `agent_template_id`, and preserves private `verifier_files` plus `verifier_template_id`. This batch rebinds 43 template-404 units proven to have zero prior inference; source and repair mappings remain explicit.
- Full source registry: `data/production-inputs-v5/plan.json`; `summary.json` seals its hash. 277 source records = 231 distinct input pairs + 42 holds + 4 aliases. Holds include 37 unclosed source executions, three capture-path mappings, and two unresolved predecessor files. Source eligibility is not execution success or SFT admission.
- Outputs: each active run's `units/<identity>/{controls,teacher,student}`; per-unit `status.json`.
- Student exports: `student/train.jsonl`, bound by `student/receipt.json`.
- Each batch owns one exclusive coordinator. Batches have disjoint logical inputs, except explicitly linked **unpaid adapter repairs**; paid attempts are never replayed.
- Matching native experts: three reusable existing trajectories; the completed Coq3 method8 attempt is preserved with its old reference-attribution hold rather than regenerated.

Preparation and setup failures are retained separately. `append-production-v1` is stopped with zero model requests after an incorrect offline-runtime directory argument. Source preparation v1–v4 and old failed alias bindings remain historical evidence, not additional data or successes.

Credentials and original model reasoning stay private. No source experiment, original receipt, grader, or failed-attempt evidence is edited.

## Validation

100 local unit checks (six SDK-dependent skips) and 100 MindLab checks (two skips) passed. Full-range streamed scoring calibration used cached proposals only: short input, an eight-candidate long input pool, and two previously interrupted candidates. It retained the same winner and validated target token IDs/coverage. One HTTP 499 required a second zero-generation score POST; all original failed evidence remains.

Source counts, expert successes and actual SFT release counts are dynamic; use the registry and per-unit receipts rather than this document as a live counter.

## First production observation

At 2026-11-03 13:30 Asia/Shanghai, the effective identity registry had 231 selected inputs: 11 native experts running, three method8 students running, four in controls, 196 queued, 15 runtime/control holds, one normal unsuccessful expert, and one completed admitted student. Four new native experts had passed final grading; students had executed 24 selected blocks. Historical unpaid adapter failures are folded through the repair mappings and never counted as extra tasks.

The first clean SFT example is Foundry Chinook unit `d2d0716acdcae4f87ffefbb8`: six executed native interactions, both independent scores one, 9,629 total tokens / 2,573 assistant-supervised tokens, no dangling expert-reference attribution, SFT hash and public-message equality checked. A one-row snapshot is at `datasets/append-method8-20261103/{train.jsonl,manifest.json}`. Each later admitted student writes its own receipt-bound `student/train.jsonl`; the snapshot is not a live counter.

`PRODUCTION_STATUS.json` is a timestamped observation. `PRODUCTION_SELECTION.json` lists the effective unit routes, so read those routes instead of summing every historical directory's raw holds.
