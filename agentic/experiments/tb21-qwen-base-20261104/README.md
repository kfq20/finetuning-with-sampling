# Qwen base Terminal-Bench2.1 baseline

CLI-Gym's original paper evaluates Terminal-Bench1.0 and2.0 with OpenHands.
This experiment establishes our own pre-SFT baseline on the corrected official
TB2.1 task set with Harbor0.23/Terminus-2 and Alibaba Sandbox.

- Dataset:89 official tasks, source commit
  `7131e4375048a0e408a8fb404b5f499d726b695b`.
- Dataset/results are evaluation-only, external to the training collector.
- Student: current user-approved self-hosted `Qwen/Qwen3.8-27B`, native HTTP.
- Plain unreferenced Pass@1: one proposal, no expert/likelihood selection.
- Preserve task-specific deadlines and minimum resources; record Alibaba-required
  resource rounding explicitly. No turn cap.
- Native nonthinking/public JSON protocol and temperature0.6 explicitly pinned.
  Standard Terminus context summarization enabled; report this configuration.
- One no-model NOP/oracle control first, then one model canary; reuse that
  task's valid first attempt in the full89-task denominator, never replay it.
- Official tests/reward are unchanged. Infrastructure/transport failures are
  retained separately from valid model0; no automatic paid model retry.
- Existing CLI-Gym16-worker acquisition is not paused or reconfigured.

## Runtime and accounting

ECS root: `/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104`.
`dataset-manifest.json` pins the original89 tasks; `images/` records digest-preserving
ACR copies. Official instructions, solution and verifier files stay byte-identical.
Original dataset files remain untouched. `evaluation-tasks/` additionally rounds
CPU/memory upward only where Alibaba's1–4GiB-perCPU constraint requires it;
`resource-allocations.json` records every difference. This is our consistent
pre/post-SFT evaluation configuration, not a leaderboard submission or exact
reproduction of CLI-Gym's OpenHands/Qwen3-32B numbers.

`run_baseline.py` reuses the original canary once, waits for normal capture and
finite official reward (a valid0 is accepted), verifies Oracle1/NOP0, then starts
only the other88 tasks at4parallel. It uses an exclusive controller lock and a
persistent dispatch receipt; transport/runtime errors never trigger paid replays.
`full-config.json`, `full-launch.json` and `baseline-summary.json` are authoritative
for dispatch and results. No benchmark trajectory enters the CLI-Gym SFT collector.

Two original no-model template failures are retained: missing registry credentials,
then ACR credentials mistakenly used with DockerHub. The successful control uses
an unchanged manifest mirrored into ACR, not credentials from another registry.

Primary references:
- https://arxiv.org/html/2602.10999v1 (§4, Table3)
- https://github.com/LiberCoders/CLI-Gym
- https://www.tbench.ai/news/terminal-bench-2-1
- https://github.com/harbor-framework/terminal-bench-2-1

## Launch snapshot (2026-11-04 23:21 CST)

- Official89-image preparation complete, manifest digests preserved.
- Actual ECS SDK regressions:124tests,122pass/2optional skips.
- `fix-git`: Oracle1/NOP0, Qwen canary1/no exception;9decisions,24terminal
  commands,53,438input/2,025output/38,912cached tokens,172.31agent seconds.
- Original canary is reused once. Remaining88 launched at4concurrent; initial
  live stats4running/84pending. See external root `launch-audit.json` for actual time.
- Five1CPU/8GiB tasks are rounded to2CPU/8GiB; all other CPU/memory requests
  preserved. No instruction/test/deadline changes.
- Existing CLI-Gym16-worker production remains selected and unchanged.

## Authorized recovery (2026-11-05)

User authorized one recovery wave after CLI-Gym acquisition reached531SFT and
no production unit workers remained. Selected exactly51AgentTimeoutError plus6
other execution errors. Retain the32normal original attempts, including10zeros.
Never select the better score across original/recovery attempts.

External recovery root: `retry57-20261105/` under the same evaluation root.
Maintained entry: `retry_failed.py`; frozen controller source1ad38c5;
agent/tokenizer/template/image/deadlines remain selectedruntime-v2. Fourparallel,
Pass@1 perselected task, no automatic extra retry. `selection.json` binds all89
original result hashes and separates selected57 from retained32. Read launch and
actual jobs rather than starting another controller.

Two unfinished requests from already-terminal original tasks were aborted by
exactrequestID through model-host loopback8131; bothHTTP200. The public proxy's
abort404 and old results are preserved. Only exactowned completed-job/controller
processes were retired; shared bridge/modelservice and other experiments untouched.
Report original run and recovery separately, then a merged cohort with recovery
outcomes replacing those57, not an iid secondPass or best-of-two score.
