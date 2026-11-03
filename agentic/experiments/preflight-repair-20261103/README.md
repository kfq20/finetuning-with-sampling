# Original-environment preflight repair — 2026-11-03

Scope: reconcile the 39 environment/verifier-only holds in append production with the original Claude Code + DeepSeek execution bindings. The census has **23 original successes and 16 original zeros**. A preflight success is not a rollout completion or an SFT admission. This work invokes no model, does not replay paid solvers, and does not modify active frozen model runtimes, original tasks, scores or costs.

## Confirmed faults and maintained fixes

| Fault | Evidence and fix |
|---|---|
| Whole `/app` was erased before restoring a partial legacy checkpoint | Original CAD adapter retained the image's project geometry and reset only output/stock/orders. Restore those original overlay semantics. Science/audio also retain their original image assets. Newly prepared legacy specs record reset paths explicitly. |
| Reward protocol assumed `reward.txt` | CAD motor's original separate verifier emits `reward.json`. Decode either original channel, require finite binary rewards and reject contradictory channels. |
| Optional diagnostic JSON treated as the scoring channel | A rejected submission can leave empty `details.json`. Preserve its hash/type as diagnostics; do not replace an explicit valid reward with JSON parsing failure. |
| Initial missing submission was classified as a broken environment | Some original science scripts exit one without writing a reward. Preserve this as `rejected_without_reward` in the no-op control, not a fabricated normal model zero; independently require the original legal submission to score one. |
| Control collector required `solution/solve.sh` | Original Foundry no-model controls are often outside the solver task. Follow task-bound hash refs and recover their actual legal captures, or replay the existing deterministic reference recipe privately. |
| Capture dialect assumed a content-addressed directory | Older controls have an ordinary `capture/manifest.json`, bound by a FileRef/capture SHA. Validate that binding plus every file digest/mode. Preserve canonical-directory identity validation for Snapshot stores. |
| Bulk transfers used short defaults / a single large write | Use bounded 1 MiB writes with request timeout 240 seconds; assemble and verify the archive hash before extraction. |
| Original verifier timeout was ignored | Read the frozen task's verifier timeout instead of a universal 900 seconds. CAD geometry checks can take many minutes. |
| A held eigenmodes item retained an inferred PENDING_BUILD alias | Reconcile against the exact original execution config's explicit template pin. Do not build images or switch to an arbitrary alternative. |
| Event evaluator used an old batch fixture | Original fresh scoring explicitly selected the published quota JSON; `tests/grade.py` instead passed an inherited fixture. A separately derived wrapper changes only that argument and adds the identical published JSON as a private input. Inherited regression fixtures and scoring rules remain intact; original package and scores remain unchanged. |

## Observed task-quality exclusions

The CAD qualification item already passes from its starting state. The event quota item also passes from its starting state after correcting the batch binding. These items are excluded from new data production rather than sent to another solver. Their original model-zero records are retained as historical records, not silently rescored or counted as new successes.

## Selected evidence and runtime

MindLab root:
`/vePFS-Mindverse/user/intern/fanqi/tb4-research/projection-agent-20261102`

- `data/preflight-holds-20261103.json`: original 39-item census.
- `PREFLIGHT_REPAIR_SELECTION.json`: explicit review roots, worker identities and current admission root.
- `data/preflight-repair-v1`: replay of 23 original successful submissions, initial rejection plus legal-positive grading in separate fresh worlds.
- `data/preflight-repair-zero-v2`, `data/preflight-reference-v3`: original-zero cases; recover original hash-bound no-model controls/reference recipes.
- `data/preflight-event-v7`: derived batch-fixture binding; initial and legal controls both one, therefore excluded.
- `data/preflight-template-v8`: exact original eigenmodes template binding; initial zero, original successful capture one.
- `data/preflight-admissions-current-20261103/report.json`: timestamped, identity-deduplicated current result.
- Its `admissions/<original-unit>/spec.json` and `certificate.json` bind reusable admissions to exact task/state bytes and modes, solver/verifier templates, healthcheck, workdir, capture paths and reset semantics. A future model worker may reuse these via `production.controls`; changed inputs cannot inherit a green certificate.

Workers and sources are persistent and frozen outside the Git checkout. The finite report publisher terminates once the selected control workers exit. It never schedules a model. Historical failed control runs and earlier reports remain available. Actual CPU-bound CAD checks are allowed to finish under the original task timeout; an in-progress check is not reported as passed.

## Code and verification

- `src/append_rewrite/grading.py`: strict reward-channel decoder.
- `src/append_rewrite/sandbox.py`: compatible reward reader and hash-verified chunked capture upload.
- `src/append_rewrite/terminus/production.py`: original overlay restoration and input-bound control reuse.
- `src/append_rewrite/terminus/{grader,control_sources,fixture_binding,preflight_repair,preflight_publish}.py`: no-model diagnostics, original evidence recovery, narrowly derived fixture binding, validation and publication.
- 105 local unit tests pass (six SDK-dependent skips); 105 MindLab SDK tests pass (two skips). Real Alibaba controls supply the domain acceptance evidence; tests alone do not establish environment acceptance.

The running model batches retain their frozen sources. These fixes are prospective maintained code plus separate no-model repair evidence. No API/teacher/candidate retry change is included in this scope.
