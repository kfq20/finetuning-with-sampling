# Native Qwen paired Coq append trial

User authorized one expert-reference and one no-reference attempt after real
native compatibility passed. Both use protocol `claude-code-v1` sample
`c110ddbf8085c8e05cb3`, byte-identical public native seed and five-file starting
state, source requirement, task/grader, pinned CLI/Harbor, model/deployment and
runtime settings. The compiled current instruction alone differs: the expert
arm includes the public expert suffix, the none arm omits it.

Entry: `python -m append_rewrite.claude_trial --prepared ... --fleet-config ...
--sandbox-credentials ... --output ... --reference-mode expert|none`.

Execute from a committed immutable source archive; private config and all state,
claims, logs and submissions live under the persistent external study root.
Each arm exclusively creates its own output directory, gateway and solver; no
provider credential enters solver. One process per arm, no automatic task retry.
Source timeout28800, no max-turns, max output128000/context1M hints, effortmax,
identical compaction settings. Do not carry the synthetic integration-probe notes
or files into these task attempts. Both start from the original protocol seed.

Before launch bind hashes to existing expert1/initial0 control receipts. Capture
native trajectory, actual output and project workspace before grading. Require
normal native termination and exact restored session ID. Score captured output
again in a fresh sandbox, preserving source and original scores. Report transport
errors separately and do not turn errors into model0. All owned sandboxes retire.

Report reward/fresh reward, CLI turns, new tool calls, agent time, total time,
usage/peak context and copy audit against expert Submission.v/proof. Exact answer
reuse is task success but is not evidence of independent rewrite or learning.
Do not export private reasoning or admit traces to training automatically.
