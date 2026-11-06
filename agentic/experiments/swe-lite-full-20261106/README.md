# SWE-bench Lite full split, rolling three-arm Pass@1

User authorized full evaluation on2026-11-06. The selected full official **test**
split contains300 tasks, distinct from the prior5-task dev pilot. Base and both
SFT arms use the same epoch1 step34 Fleet deployments as that pilot; epoch2 is
not silently substituted. One paid attempt per task per arm, maximum900.

Frozen protocol: Terminus-2, nonthinking, temperature.6, context262144/output128000,
agent1800s/no max_turns; official eval/checks/parser, verifier1800s. The grading
wrapper runs in base conda Python while official tests activate their original
testbed Python. The greater verifier allowance affects grading only, not solver
budget or required tests. No automatic paid retries; errors remain unknown.

Four independent gate workers mirror exact image digests to owned ACR, inject
only the already-tested offline tmux runtime, then run actual install-only,
NOP0 and gold1. Each admitted task immediately joins three independent model
queues,4workers per arm (12models maximum). A broken task doesn't hold up others.
The source/test/gold remain separated from solver input. No original task is
simplified, no failing check is dropped. Mirrors stream registry-to-registry;
no huge Docker image is pulled onto the ECS disks. Runtime archives are hardlinks.

Metadata and checkpoint are checked before each model claim. Persistent
controller/task claims prohibit accidental restarts/replays. Low disk pauses
new dispatch at2GiB free; active attempts continue, with the reason in
storage-hold.json. STOP prevents new claims without killing current models.
Existing TB2.1 and epoch2 training are untouched.

Explicit test selection:
`/mnt/ecs-tb4/evaluations/qwen38-swe-lite-test300-20261106-a1`.
`active_runtime_selection.json`, launch and source-files bind code/data/model
identities. `progress.json` separates admitted/held, claimed, valid, full-success,
execution-unknown and pre-model holds. `finished.json` is written only after all
queued gates/models end. Do not choose newer roots by suffix or call900 planned
attempts completed. This is official Lite test, not the23-task development split.

Sources and pipeline assets are reused from the verified pilot; raw traces,
private configs and large runtime assets stay outside Git. The branch
study/swe-lite-full-20261106 contains maintained orchestration. A dev-only mode
can explicitly import the15 prior paid results and exclude those5 tasks from
new requests; it is not the selected test300 protocol.
