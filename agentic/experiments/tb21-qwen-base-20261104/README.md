# Qwen base Terminal-Bench2.1 baseline

CLI-Gym's original paper evaluates Terminal-Bench1.0 and2.0 with OpenHands.
This experiment establishes our own pre-SFT baseline on the corrected official
TB2.1 task set with Harbor0.23/Terminus-2 and Alibaba Sandbox.

- Dataset:89 official tasks, source commit
  `7131e4375048a0e408a8fb404b5f499d726b695b`.
- Dataset/results are evaluation-only, external to the training collector.
- Student: current user-approved self-hosted `Qwen/Qwen3.8-27B`, native HTTP.
- Plain unreferenced Pass@1: one proposal, no expert/likelihood selection.
- Preserve task-specific resource requests and timeouts, no turn cap.
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
