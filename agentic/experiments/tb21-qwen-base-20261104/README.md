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
