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
Target:531 additional successful method/expert pairs,1062 total; source yield
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
