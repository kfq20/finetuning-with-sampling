# CLI-Gym data-size and distribution diagnostic

Selected external root: `/mnt/ecs-tb4/cli-gym-expansion-20261107`.
Frozen source pool: LiberCoders/CLI-Gym revision
`552945c5aaf07d9715549a798c98ee13bb5b7f06`, 1655 rows, official train split.

This is an internal test split, not an official CLI-Gym validation/test split.
100 previously unprepared and undispatched tasks, spanning19 source images,
are frozen before model evaluation. Selection uses outcome-blind seeded hashes
and excludes exact instruction/fault/grader contract duplicates of all prior
dispatched tasks. Same repositories may occur in training: this measures
in-distribution unseen-task transfer, not unseen-repository generalization.
Do not replace held-out tasks based on model success or environmental failures;
report planned100, admitted count, valid three-arm intersection and unknowns.

`freeze.py` verifies all source pages and the original SFT bytes. Original531
training tasks and863 historical dispatched task IDs remain excluded from new
acquisition. After contract deduplication and test reservation,680 undispatched
candidates remain,48 not previously preparation-scanned and632 scanned earlier.
They are candidates, not680 executable environments or admitted SFT examples.
Current user priority:469 additional successful method/expert pairs,1000 total; source yield
may make this unattainable without additional data. Never relabel duplicates
or replay failed paid attempts to meet the target.

`prepare_selected.py` is a finite no-model worker: first prepare100 held-out
environments, then48 fresh acquisition environments. It uses the pinned prior
builder and study-owned Docker socket, with an owned copy raising storage
admission from20 to40GiB. Original images, experiments and sources stay intact.
It builds packages; healthy/initial/verifier controls remain required before
model admission. It does not launch an expert, student, training or evaluation.

Next stages:

1. Repair infrastructure blockers for remaining undispatched candidates without
   weakening test assertions; preserve original failures. Freeze corrected
   package identities and require healthy1/initial0 controls.
2. Generate new paired data with the existing8-candidate method and corresponding
   DeepSeek expert, using an explicitly selected live Qwen route and tokenizer.
   Keep internal100 completely out of both expert and student data generation.
3. Evaluate base, method-SFT and expert-SFT on internal100 using the same
   harness, timeouts and model settings. Keep epoch1 and epoch2 results separate.
4. Compare531 vs1062 matched-task paired SFT at the same recipe and epochs.
   Also compare original531 with equal sample/token exposure to separate new
   diversity from additional optimizer work. Report supervised tokens per arm.
5. Interpret CLI-Gym gains separately from TB/SWE transfer. More data alone is
   not evidence of stronger general capabilities; training loss is not a proxy
   for held-out score. Keep SWE test data out of recipe/data selection.

Status and evidence live in `split-v1/summary.json`, `selection.json`, preparation
launch/progress/finished receipts and per-task preparation logs. No automatic
paid retry, second legacy coordinator or change to ongoing SWE evaluation.

## Selected acquisition,2026-11-07

The1000-pair objective supersedes the earlier1062 target only. New-source and
multi-expert ablations are deferred. New root `goal.json` is authoritative.
One new-task canary (row1517) passed initial0/healthy1, DeepSeek original1/fresh1,
and Qwen8-candidate original1/fresh1 with SFT admission:532 total at first closure.
The existing production coordinator owns16 slots; candidate scores use4 slots.
Task processes include pre-model controls: slots are not16 simultaneous students.

Network-none manufacturing blocked genuine dependency downloads. Repair builds
may use host networking; solver containers remain network-none without host
mounts or credentials. Reachability checks found Ubuntu origin unavailable and
Huaweicloud/Aliyun mirrors reachable. An explicit prerequisite-only apt mirror
prelude is recorded in the new Dockerfile; final image IDs and task manifests
are frozen. Source recipes, instructions and test assertions remain available.
Nested test paths are frozen from the healthy image; malformed selector quoting
is resolved only through a unique mapping to real collected IDs. Exact repeated
selectors are deduplicated, while ambiguous mapping stays held. Full-suite
published tasks use all gold-collected IDs, not an invented small subset.

Selected producer/preparer:source5c61542, `acquisition-mirror-launch.json`.
Original live coordinator remains source3fbaa08, `coordinator-launch.json`.
The canary remains sourcebb8409b. Explicit `active_runtime_selection.json` binds
these roles; version suffixes are not selection rules. Only the unpaid producer
and preparer were replaced; the coordinator and paid workers were preserved,
with evidence in `unpaid-build-handoff.json`. Old partial builds and holds stay.

Initial-already-passing tasks stay excluded;91 such historical zero-model holds
were identified. Other healthy-control failures (including pytest plugin/process
compatibility) remain unpaid holds until repaired and independently recalibrated.
No failed paid attempts are replayed and no hold is promoted into training data.
40GiB storage admission applies to both preparation and future dispatch.

Detailed blocker taxonomy, strict calibration controls and source-role bindings: [ENVIRONMENT-REPAIRS.md](ENVIRONMENT-REPAIRS.md).
