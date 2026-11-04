# CLI-Gym production expansion — 2026-11-04

Goal: 500–1000 distinct, scored, format-validated student trajectories. Candidate
generations and expert trajectories do not count toward that goal. No weight
training or training gain is claimed by acquisition.

The six-source pilot closed with four successful experts, three admitted
students and one student upstream502. Two other sources failed pre-model gates.
All original attempts and costs remain intact, with no automatic paid retries.

Wave1 uses the remaining94 of the already-frozen official rows0–99, excluding
pilot rows1/15/16/29/46/87;22 projects occur across those100 rows. Selection is
by original row index, never by model success. This first expansion is not a
claim of500 completed samples. Later waves must use new source identities and
update the explicit selection rather than silently extending a frozen plan.

Execution reuses the pilot's committed prepare/launch entries and Terminus-2
pipeline. Prepare now accepts explicit row indices, groups by original base
image and optionally repairs quote/backslash selector transport by unique
collection mapping before any paid dispatch. Original instructions, tests,
assertions, recipes and old failed gates remain retained.

Controls require initial0/healthy1 before expert inference. Expert must have
normal completion and original1/fresh1 before the student starts. Student uses
the full expert reference,8 proposals per action block, reference-free student
logprob ranking, and only executes the selected action. Original1/fresh1,
private-path/reference-attribution checks and assistant-only label validation
precede SFT publication. Generation errors stay errors, not model zeros.

The new controller and its large artifacts live on the ECS data disk:
`/mnt/ecs-tb4/cli-gym-scale-20261104`. MindLab's root has insufficient free space
for this wave. It uses the existing study-owned private Docker daemon; neither
shared Docker nor existing images/experiments are changed. The exact SDK package
copy is tested on the ECS Python3.13 runtime before dispatch. Credentials stay in
private controller support, never solver containers or Git.

Four task lanes, target4 student slots and2 score-prefill slots. Native task
timeouts remain unchanged. No new model-turn cap, credential fallback, automatic
paid retry, author session, subagent or recurring automation is introduced.
Old TB4 USER_STOP remains in force. No source task is dispatched twice.

`collect.py` validates receipt/SFT hashes, final scores and loss-mask consistency,
deduplicates input identities and atomically publishes a cumulative JSONL and
manifest. It may run as a finite read-only follower until the coordinator closes;
it cannot send model requests or dispatch tasks. Preserve source receipts,
snapshots, rejected candidates, failures and costs independently of this export.

Operational authority: `active_runtime_selection.json`, explicit prepared plan,
source commit and process launch identities. Model teacher remains approved
DeepSeek Flash/mintcn; student remains the existing Qwen3.8-27B Fleet deployment.
Do not choose a runtime by largest version suffix or call a launcher an inference.

`campaign.py` freezes the remaining public source pages with revision checks,
observes wave1 without relaunching it, then serially admits new100-row waves.
Each later wave has an explicit selection and exclusive launch. Only one wave
dispatches at a time, retaining the4/2 student/scorer setting. It publishes the
canonical `campaign-sft/train.jsonl` and `manifest.json`, and stops after a wave
reaches500 admitted trajectories (at most99 additional successes in that wave),
or on source exhaustion, low data-disk space, provider stop or infrastructure
failure. It cannot guarantee500/1000 positives from a finite1655-source pool.
This is a finite authorized production worker, not a recurring automation.
Its separate `campaign-selection.json` identifies future-wave code; it never
changes wave1's frozen source or repeats a paid attempt. A held campaign needs
diagnosis rather than blind restart, because later-wave launch records are
exclusive and original attempts must not be repeated.
