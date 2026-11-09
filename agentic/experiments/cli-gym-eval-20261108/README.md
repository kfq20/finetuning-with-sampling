# Frozen CLI-Gym heldout evaluation

Evaluate the previously frozen100-task internal CLI-Gym holdout without expert
reference or candidate selection. The first selected built task is a real
canary; a valid0 is sufficient to release the remaining queue. Two independent
worker processes run afterward, preserving per-task wall-clock cancellation.
No failed or uncertain model attempt is automatically replayed.

Selected base run:
`/mnt/ecs-tb4/evaluations/qwen38-cli100-base-http-20261108-a1`.
Read its `active_runtime_selection.json`, `launch.json` and actual process state.
The base endpoint is the already authorized direct HTTP Qwen3.8-27B service.
Existing production processes,16 task slots and32 scoring slots are unchanged;
the evaluation adds2 workers sharing inference capacity.

Protocol: pinned Harbor0.23 Terminus-2 JSON harness, frozen tokenizer/template,
nonthinking, temperature0.6, context262144, output cap128000 bounded by remaining
context, original per-task episode timeout. Each decision makes one generation;
there is no expert prompt, likelihood ranking, student-data export or training.
The same protocol and frozen task specs are intended for both Epoch2 adapters
when Fleet deployment authentication is restored. Service-specific latency must
be separated from model capability when comparing direct HTTP and Fleet.

`prepare` reuses66 previously built heldout packages, then attempts original
Docker builds for the remaining34 with build-time networking. It does not run
per-task gold/NOP/mutation calibration or change the heldout roster. Build,
packaging and startup failures stay separate from model failures. No easier task
replaces a failed environment. Missing published assets or unsupported scoring
formats are recorded as preparation failures, not evidence the upstream task is
unsolvable. Preparation waits below40GiB free space and does not delete images.

`run` launches one exclusive `trial` subprocess per task. It reuses the maintained
production episode through an explicit evaluation-only backend. Full filesystem
capture and two fresh grading worlds preserve system-level repairs. A normal
trial with matching binary grades is valid; inconsistent grades or execution
exceptions remain unknown. All required checks must pass for binary1. The
result includes the frozen task spec hash. Original score/capture evidence is
retained; a failed canary holds bulk dispatch for diagnosis.

Evidence:
- `plan.json`, `holdout-selection.json`, `runtime-binding.json`
- `model-info.json`, `regressions.json`, `launch.json`
- `tasks.json`, `preparation-progress.json`, `preparation-complete.json`
- `health.json`, `canary-selection.json`, `trials/*/result.json`, `summary.json`
- `generation/*/turn-*/decision.json` for usage/context/latency

Private endpoint credentials stay in mode-0600 controller files, outside solver
and verifier inputs.

## Matched Fleet comparison

The selected three-arm comparison is
`/mnt/ecs-tb4/evaluations/qwen38-cli100-epoch2-fleet-20261109`. The historical
401 receipt and direct HTTP Base evaluation remain separate records. The new
Base and both step-68 adapters run on the same Fleet H20 cluster. The launcher
checks the live deployment source, checkpoint and cluster for each arm, then
tests the exact native streaming client with a pinned token prompt.

`compare.py launch` accepts its private configuration on stdin. Each arm uses
the same frozen 100-row selection, a common task manifest, one attempt per
task, and two slots after its canary closes. The original 70 prepared specs are
hash checked. `prepare_remaining.py` attempts targeted repairs for eligible
preparation holds at one build at a time, with a 55 GiB free-space gate.
Missing build context and recipes requiring a separate semantic repair stay
explicitly held. Repair candidates enter all three arms through the same
manifest. The inference controllers use the existing 40 GiB gate.

`compare.py report` records raw arm totals and the three-way valid intersection,
including binary success percentages on the same tasks. Final grading requires
agreement between two fresh verifier worlds. A deployment probe has no task
score, and an infrastructure hold remains outside the valid intersection.
