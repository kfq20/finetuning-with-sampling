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

Private endpoint credentials stay in `private.json` on the controller, outside
solver and verifier inputs. The comparison Epoch2 deployment is independently
held at `qwen38-cli100-epoch2-20261108-a1/HOLD.json` after Fleet returned401
`invalid api key`; this base run does not clear that hold or substitute Epoch1.
