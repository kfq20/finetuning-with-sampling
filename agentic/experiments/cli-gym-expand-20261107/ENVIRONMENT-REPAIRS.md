# CLI-Gym environment supply repair,2026-11-07

## Afternoon follow-up: supply and throughput

The selected producer still uses5f808e2. The prospective coordinator now uses
base3fbaa08 + teacher43b16ee + opt-in grader628099d. Repeated rolling handoffs
retain both direct children and workers adopted by an earlier coordinator,
including orphaned PPID1 workers; capacity remains16, score capacity4. Receipts
are under `support/supply-throughput-20261107/` and
`support/qwen-http-student-20261107/`. Check current selections before operating.

Real pytest-relaxed output exposed two display assumptions: per-item outcomes
were trees, and the private canary was legitimately collected twice. The opt-in
repair adds pytest `-rA`, requires each exact required node ID to pass in its
summary, retains failures across duplicate reports, and requires the exact
private failing assertion with exit1 instead of a literal `1 failed` count.
Legacy contracts remain unchanged. Initial0, healthy1 and public-test-code
mutation controls admitted5 environments (pilot1 + batch4). Four additional
rows failed the extra mutation calibration and remain held; two were already
passing before repair and remain excluded. No test/assertion was dropped.

A separate current collection-only adapter recovered9 of14 previously
unprepared task packages;5 still fail genuine gold collection. The9 packages
join production controls before any model request. These are not9 SFT records.
Both finite repair batches finished and their plans are registered with the
existing producer; total published packages reached595 from581.

Timing census of45 successful new pairs: teacher mean127.1s; student1503.3s;
student mean6.78 blocks. Across2440 candidate generations mean39.3s/median14.0s;
2437 scoring calls mean9.0s/median4.0s. Time between generation completion and
first scoring POST (rendering plus slot wait) mean47.2s/median17.0s. This is a
successful-cohort profile, not an uncensored estimate for all active attempts.
Active-block inspection found individual unfinished candidates aged19–27min
with only hundreds to~1280 reported tokens. All16 task slots were occupied.

Read-only model-host checks found8 H20 GPUs at100% utilization, TP4/DP2, with
continuous prefill/decode activity. This does not alone establish the cause of
an individual stalled stream. Increasing task slots was not selected as a fix.
A suffix-logprob transport probe returned fewer bytes but differed from its
paired full-logprob score by0.0005601, exceeding the probe tolerance; it was NOT
deployed. The selection formula, eight candidates and score capacity remain
unchanged.

The audit also found expansion bootstrap inherited the old canary's SSH Qwen
config (`127.0.0.1:18131`), despite the prior HTTP-direct authorization. A new
private config selects `http://123.57.26.97:8000/generate` with the already
authorized credential, same model/context/template. A zero-generation replay of
an existing candidate verified all input IDs and reproduced the previous mean
logprob exactly. Subsequent new units select HTTP directly; already-paid units
keep their original configuration. No solver attempt was replayed. Maintained
bootstrap now honors explicit selected teacher/student config pointers and
fails closed if they are absent, rather than falling back to old canary routes.

The transport correction is selected, but speedup must be measured on actual
new HTTP units; it is not established by the probe. Original531, held-out100,
all previous scores/failures, credentials and paid attempts remain preserved.

The objective remains1000 admitted method/expert pairs. No failed paid model
attempt is replayed; original results, costs, source packages and failed
preflights remain evidence. The internal100-task test selection stays excluded.

## Observed recovery

Snapshot at12:43 CST:558 admitted trajectories (531 original +27 new),573 task
packages published, configured task capacity16 and scoring capacity4. A separate
live audit verified16 actual production unit processes, not16 simultaneous
students. The coordinator remains the original source3fbaa08/PID248831; only the
unpaid producer was handed off. Current PID identities must be rechecked.

| Blocker | Repair | Evidence at this snapshot |
|---|---|---|
| Manufacturing could not download prerequisites | Host networking for owned builds only; reachable prerequisite mirrors; solver stays network-none | Eight dependency/Bash repair packages prepared; individual controls still precede model dispatch |
| Shell uses Bash syntax under `/bin/sh` | Explicit Bash build interpreter, preserving the original fault commands | Included in the same eight build packages |
| Classes/parameter aliases interpreted as missing test IDs | Expand all collected children; map aliases only to uniquely identified real tests | Four pilot +35 batch packages recovered |
| Verbose/unittest console trees contain no node-ID lines | Capture actual `session.items[].nodeid` through a collection-only pytest hook | Seven further packages recovered; one unresolved source mismatch remains held |
| Host CPU count triggers too many pytest/BLAS workers | Bound process/thread allocation and serialize installed xdist; preserve every required test | Nine independent initial0/healthy1 resource admissions at the snapshot |
| Damaged business fixtures accidentally frozen as verifier assets | Restore immutable test/oracle assets while preserving submitted task-data contents | Eight fixture admissions, each requiring positive/negative and tamper controls |

Prepared packages and control-admitted environments are different stages. Neither
is SFT data until both model episodes meet the existing full-success and export
admission checks. Counts above must not be summed into a training-data count.

## The fixture boundary defect

Cantools row580 modifies three operational files:
`tests/files/dbc/multiplex.dbc`, `multiplex_choices.dbc` and
`tests/files/kcd/the_homer.kcd`. The old archive copied the entire damaged
`tests/` directory. Restoring that archive contaminated the healthy verifier
world with the same damaged inputs. Python test-source bytes were unchanged.

`repair_fixtures.py` compares the frozen old archive with the immutable healthy
reference. It permits only changed operational data formats explicitly named,
or covered by a literal directory token, in the original fault recipe. A Python
test-code difference rejects automatic repair. Test assertions and required
test IDs are retained. Every other non-cache verifier asset stays immutable.

The private grading wrapper stages the actual submitted task data, restores the
immutable assets and removes unexpected test-tree additions, then reinstates
the submitted data before running the unchanged required tests. Missing data
is not silently restored from the reference. Solver instructions and the initial
faulted filesystem remain unchanged; the private reference is never uploaded to
the solver episode.

Actual row580 controls:

| Control | Required checks passed | Binary result |
|---|---:|---:|
| Faulted initial world |14/18|0|
| Healthy reference |18/18|1|
| Healthy world with required task data removed |17/18|0|
| Faulted world with public test code replaced by blanket-pass stubs |14/18|0|

Later directory-wide fixture repairs delete the entire declared mutable set in
the missing-data control. The failing private canary must remain operational in
both negative mutations. All mutations are no-model experiments on disposable
owned worlds. Source455 remains held because its archive also changes Python
test code; no assertions were removed to accept it.

## Scope and execution safeguards

- `select_control_holds.py` excludes any historical source row with a teacher or
  student attempt directory, and excludes paid semantic duplicates.142 closed
  pre-model parents were selected. Additional directory discovery found zero
  paid-attempt conflicts in that selection.
- `repair_controls.py` rechecks this proof before calibration and publication.
  The resource overlay verifies identical RootFS layers, actor, entrypoint and
  command metadata; only declared resource environment variables change.
- `acquire.py` consumes the separately registered repair plans. It rechecks
  source scope, test exclusion, proof hashes and full initial0/healthy1 results
  for repaired pre-model holds. The existing coordinator and paid workers are
  observed and preserved, never restarted during the producer handoff.
- Producer source5f808e2, main preparation source5c61542, collection adapter
  source6bf7212, resource adapter8c6c4eb and fixture adapter42917dc are separate
  frozen roles. Git HEAD does not replace any running source automatically.
- The first resource-overlay attempt used an unsupported BuildKit `FROM
  sha256:...` reference. Those zero-model failures remain recorded. The fix
  binds a verified owned local image alias; this was not a model-provider auth
  failure and required no credential changes.

## Remaining holds

These are not valid model failures or training examples:

- Published required test IDs absent from the pinned project version: retain
  the requirement and hold; do not guess a nearby test or drop the check.
- Healthy worlds with actual failed or skipped required tests: retain the
  full-pass requirement. A baseline skip is not upgraded to a pass.
- Nonstandard pytest plugins whose private rejection control fails: hold until
  independently calibrated; do not disable the negative control to gain supply.
- Network-dependent gold tests under the selected offline solver policy, global
  runtime faults preventing trusted setup, unavailable build-context files and
  damaged source recipes: preserve per-task evidence and unresolved status.
- Slow unpaid controls retain the original verifier deadlines and run separately
  from the16 production slots; they do not block existing model work.

## Live evidence

ECS root: `/mnt/ecs-tb4/cli-gym-expansion-20261107`.

- `active_runtime_selection.json`, `goal.json`, `acquisition-progress.json`
- `environment-repair-plans.json`, `environment-repair-live-summary.json`
- `producer-handoff-env-repairs-20261107.json`, `producer-handoff-selection.json`
- `legacy-control-repair-selection.json`, `legacy-unpaid-broad-scan.json`
- `environment-blockers-initial.json`, `remaining-control-blockers.json`
- `resource-overlay-pilot/`, `control-repair-batch-v2/`
- `fixture-boundary-pilot/`, `fixture-boundary-batch/`, `fixture-directory-repair/`

Each repair directory contains source binding, immutable input identity, control
receipts and rejection evidence. Failed and superseded directories are retained.
`campaign-sft/manifest.json` is the current cumulative data pack; the original
531 release remains at its original path and hash.

## Quantity-first follow-up,2026-11-08

The user explicitly prioritizes qualified data volume over resolving every source
fault. Unrecoverable or expensive environments should be skipped while the
existing source queue continues. The private filesystem prototype remains in a
separate unselected branch; it is not part of production or the skill.
Actual row861/1492 diagnostics reached the tmux smoke after private reset, but the
source's corrupted libc search path also prevents ordinary shell/runtime startup.
Those cases remain held. No solver request or task-tool replacement was made.

`inventory_expert_reuse.py` is a read-only audit for a possible additional student
sampling wave. It checks native expert admission, both full scores, input identity,
source spec and public-history bytes. It does not admit environments, dispatch
students or authorize repeated samples. The actual inventory found596 exact native
experts with source/history bindings;8 entries need separate provenance review.
Additional student sampling is pending explicit user selection. Any future sample
must get a distinct identity and preserve the original attempts, grouped task
split and all current scoring/quality criteria.

ECS evidence: `support/cli-control-fs-20261108/tmux-diagnostic.json`,
`controlfs-pilots-v2/complete.json`,
`support/expert-reuse-inventory-20261108/inventory.json`.
The SWE manufacturer was live with56 prepared environments,5 held, and a full
16-task unpaid queue; the model controller and producer identities were unchanged.
CLI604/SWE5 is the observed admitted count, not target completion.

A repeated direct-HTTP zero-generation check on the same4669-token saved input
found full-a/full-b candidate mean LP identical(-0.12875317445692488). Suffix-a
and suffix-b differed by0.0016132591; full-a versus suffix-a differed by0.0022862867.
Both transports passed the existing candidate token-ID alignment checks, but this
does not establish numerical equivalence. The suffix response was~4.3KB versus
~172KB full; that byte reduction is insufficient evidence to change scoring.
The shortcut remains unselected. No original decision, generation, action or
production scorer was changed; four zero-generation calls used the existing
four-slot admission pool. This observation does not identify an exclusive server
or numerical-kernel cause. Evidence:`support/score-range-recheck-20261108/` and
`agentic/research/evidence/score-range-recheck-20261108.json`.


## Verified SWE-Gym fixture repair (2026-11-08)

MyPy generates pytest nodes from `test-data/` files. A gold collection can see a
new node while grading an archive containing only `mypy/test` collects none.
New MyPy packages now validate the canonical test patch is confined to those test
roots, freeze both trees, and explicitly use installed xdist's serial mode.
The private negative canary also uses serial mode. Test IDs, expectations and
business source stay unchanged; initial control must demonstrate a real published
FAIL_TO_PASS failure, followed by all-required gold and fresh success.

Actual10432 calibration passed initial0/gold1/fresh1 and a failing assertion
canary. Sixteen additional new-contract controls passed. These are environment
admissions, not sixteen SFT rows. Selected runtime720746d and control/receipt
hashes are recorded in `research/evidence/mypy-fixture-source-recovery-20261108.json`.

For a busy unpaid source maker, `handoff_swe_maker.main(..., drain=True)` sends
SIGINT only to the verified Python maker PID. Its existing ThreadPoolExecutor
finishes all in-flight futures before process exit; no verifier child or paid
model worker is signalled. The replacement waits for verified exit, keeps the
original folders, and uses a new output identity. Drain-time unpublished results
must be accounted for from the saved progress and actual control receipts; do
not replay a model or infer paid completion from this source lifecycle change.
