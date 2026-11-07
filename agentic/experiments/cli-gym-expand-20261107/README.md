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

## Teacher endpoint switch,2026-11-07

The user authorized `deepseek-flash` on `https://mint.macaron.im` after the old
mintcn credential repeatedly returned `group requests-per-minute limit exceeded`.
The new route passed a real Anthropic streaming probe with the production
128000-token limit, adaptive thinking and max effort: model identity matched,
`end_turn` and `message_stop` were observed, elapsed1.05s. This establishes
transport compatibility, not sustained throughput or a different underlying model.

The selected external evidence is `support/mint-im-switch-20261107/`:
`policy.json`, `probe-result.json`, `runtime-binding.json`, `before.json`,
`handoff.json`, `adopt-workers.json` and `postcheck.json`. The frozen coordinator
uses base3fbaa08 plus the teacher-only patch43b16ee; the producer retains5f808e2.
`switch_teacher.py` is the committed one-shot handoff operator. Its execution
adopted16 existing paid unit processes without restarting them. Those units keep
their original route; new units use the new private teacher config.16 task slots,
4 scoring slots, student route, test split and admission criteria remain fixed.
Existing errors and completed attempts are never replayed.9 transport/production
regressions passed in the actual ECS SDK environment. Secrets are external0600
files; request intents record endpoint and credential/policy digests only.


## Incident repair and independent source goals, 2026-11-07 evening

The user clarified two independent goals: **CLI-Gym1000 plus SWE-Gym1000**,
not a mixed1000 release. `goal.json.targets_by_source` and
`production/source-targets.json` bind the two quotas. The producer exports
`campaign-sft/{cli-gym,swe-gym}/{train.jsonl,manifest.json}` separately and stops
only when both targets are reached. The original531 and all paid attempts remain
immutable.100 reserved CLI tasks and the SWE-bench Lite300 test IDs stay excluded.

| Finding | Repair and evidence boundary |
|---|---|
|37 new-route teacher502 responses | Original upstream-error messages are retained. Shared provider admission pauses new tasks and runs bounded independent health probes; no failed benchmark replay or fallback. A small health probe recovered, not proof that the upstream incident can never recur. |
|30 student episode timeouts | Each reached the3000-second episode deadline. Generation/transport and queue waits consumed the same budget. HTTP client waits of488–509s versus server work of2.85–15.8s show a transport/front-end delay; they do not identify one exclusive upstream component. |
|Candidate transport | New tasks use direct native HTTP JSON with async cancellation and owned-request abort.8 proposals, reference-free full-input logprob ranking, tokenizer/template and task scoring are unchanged. Existing paid students retain their original bindings. |
|Bootstrap failures | Long scripts use stdin, directory copies and checksum verification use Docker API, resource wrappers are idempotent, permission tests use their required UID65534.20/69 selected unpaid repairs passed;49 remain held. No dropped assertions, skip-as-pass or initial-already-successful admissions. |
|False healthy idle / storage termination | Runtime health reports actual worker counts and supply/storage holds. Storage pauses new dispatch rather than writing a terminal provider stop. Adopted paid workers remain observed during admission holds. Exhausted supply gets an explicit blocked status. |

Selected production source iscc7c7e6, frozen under
`support/dual-source-adoption-20261107/runtime`, with an explicit rolling handoff
that retained4 paid workers. The independently frozen source manufacturer uses
802262d under`support/dual-source-goal-20261107/runtime`; it waits at40GiB free
and preserves previous holds. Read current selection/receipts rather than PIDs
or version suffixes.7 production and12 source-contract regressions passed in the
actual ECS SDK; earlier transport/Docker/scoring suites remain recorded.

The SWE source manifest freezes2438 official train rows, source revision/row hashes
and eval exclusions. Actual initial0/gold1 controls precede each admission. Git
patch capture binds the authentic initialized repository, including preinstalled
dependency edits, and preserves binary/untracked/agent-committed changes. Private
gold code and test patches never enter the solver environment. Unsupported or
inapplicable published patches remain unpaid holds.

At23:20 CST, CLI604/SWE1 were admitted, with3 actual workers still running.
Capacity16 is not the number of busy workers: disk admission was holding new
supply at~39.5GiB free. Closed journals were losslessly compressed with full
uncompressed SHA checks; SFT, receipts, decisions, original failures and all images
were preserved. `.json.gz`/`.jsonl.gz` files and their ledgers are authoritative
raw evidence, not disposable cache. No image cache deletion was authorized.

Operational evidence: `support/resume-supply-20261107/`,
`support/resume-source-20261107/`, `support/dual-source-goal-20261107/`,
`support/dual-source-adoption-20261107/`. `census_cli_supply.py` audits unused CLI
contracts and teacher-only reuse candidates without any model requests.


## Storage lifecycle and dispatch correction, 2026-11-08

Current coordinator:c78cef6 at`support/dispatch-repair-20261108/runtime`.
The earlier admission helper incorrectly resolved a function imported only inside
`batch`, killing fresh lanes while adopted workers remained observed. A real
fresh-admission regression reproduced it. The correction and lane failure gate
preserve paid workers, retain unclaimed scopes, and surface dispatcher failures
instead of reporting healthy idle.14 previously unclaimed tasks received their
first attempts;886 original terminal evidence files verified unchanged.

Producer:a835dca at`support/storage-lifecycle-20261108/runtime`; all model-library
Python files are byte-identical to the coordinator library. Producer-only handoff
kept the coordinator and all model workers. `storage-policy.json` records the
user's proactive cleanup authorization. `maintain_storage.py` performs finite
passes inside this existing producer lifecycle, using only the owned CLI Docker
socket. It losslessly compacts settled closed journals and, below100GiB free,
checks completed SWE source images for no queued/container/CLI references and
exact remote registry config before eviction, aiming for120GiB free. It does not
prune Docker globally, replay model attempts, remove training evidence, or create
an independent model supervisor/automation. Every pass has a launch/receipt.

The late cleanup deleted30 reproducible old export-cache archives after checking
their original immutable registry sources and preserving exporter code/metadata;
142.67GiB physical allocation reclaimed. One unpinned archive stays.3 separately
approved new source image caches reclaimed2.93GiB. Existing loop filesystems were
trimmed online without deleting files/snapshots or changing logical capacity;
physical root recovery was1.55GiB, not the much larger logical discard display.
`/mnt/ecs-tb4/audits/storage-cleanup-20261107-late` is authoritative. Rebuilding a
removed compressed export requires a new transport receipt/hash; original receipt
bytes are historical evidence and must never be silently rewritten as new proof.

00:42 CST: CLI604/SWE2 admitted,16 actual workers/15 queued. Original531 and all
old errors/costs remain; new source manufacture consumes space as it proceeds.
For current counts use source manifests/progress plus actual process identities.
The independent CLI1k and SWE1k goals remain active.

The quantity-first follow-up skips costly source-runtime faults rather than
repairing every environment. Read `ENVIRONMENT-REPAIRS.md` for the unselected
private-filesystem pilot and read-only expert reuse inventory. The latter is
preparation only; it does not dispatch additional samples or override no-replay
policy. CLI and SWE quotas and quality gates remain independent.

Prospective scoring can opt into`APPEND_REWRITE_SCORE_FIFO=1`. Locked tickets
provide FIFO admission over the same four legacy-compatible score slots; crashed
waiters are reaped by lock ownership, not elapsed time. Successful score receipts
record`score_queue_wait_sec`. No sampling, full-input likelihood computation,
selection, model retry or task admission rule changes. Existing paid workers keep
their original runtime. This prevents new waiters repeatedly overtaking queued
scores; it does not increase scoring capacity or guarantee shorter model work.

The FIFO runtime217af79 was selected through an identity-checked rolling handoff
at2026-11-08 01:32 CST. All16 original paid workers were adopted;943 original
terminal files and the531 baseline hash remained unchanged. Actual ECS SDK tests:
4 scoring/queue,9 production and4 handoff checks passed. The same teacher/student
routes and four score slots remain selected. New workers inherit FIFO; adopted
workers retain their old libraries and environment. Do not report a measured
speedup until prospective queue-wait receipts exist. Before the change,246
candidate pairs from two timed-out episodes had generation-response to first-score
intent waits of median38.1s/mean78.5s/max424.1s (rendering plus slot admission).
Authoritative deployment evidence:`support/score-fifo-20261108/`, including the
runtime binding, probe result, handoff, postcheck and actual worker audit.

## Paired training export,2026-11-08

ECS dataset selection:`/mnt/ecs-tb4/datasets/paired-expansion-20261108/SELECTED_RELEASE.json`.
The immutable`snapshot-v1` contains CLI604 pairs and SWE7 pairs, each source with
`package/method-paired/train.jsonl` and`package/expert-paired/train.jsonl`.
The established offline exporter and validator verified original/fresh full scores,
reference removal, matching ordered input identities, labels, assistant loss masks
and full frozen-tokenizer re-encoding. All611 pairs passed, zero pair holds.
Source manifest/train bytes were consistently snapshotted before export; live
production and all original evidence remain untouched. This did not invoke a model
or start training. Maintained finite wrapper:`paired_snapshot.py`.
The local evidence summary is`agentic/research/evidence/paired-expansion-20261108.json`.
Do not confuse this immutable export with the producer's live cumulative counts or
with reaching the independent1k goals.

The first pressure-triggered cache pass removed12 completed source caches,
recovering6.55GiB net while production continued. It also exposed stale candidate
starvation: already-removed IDs consumed the16-item attempt allowance. Patch
cc63b2e filters candidates through actual resident image IDs before applying the
limit, preserving all queue/container/CLI protection and registry-digest checks.
Fourteen actual SDK source/storage tests passed. Frozen producer-only follow-up
`support/storage-lifecycle-v2-20261108` (base217af79 + patchescc63b2e/f0c1ab8)
contains byte-identical model libraries. Its identity-checked handoff retained
coordinator2805293 and signalled no model workers;969 prior terminal files remained
unchanged. Current identities remain subject to live verification. Read explicit
`producer_runtime` and`coordinator_source_commit` separately, rather than assuming
that all roles run Git HEAD. No automatic paid replay or shared Docker operation.
