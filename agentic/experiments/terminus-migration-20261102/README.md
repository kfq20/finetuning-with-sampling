# Native Terminus-2 migration

User requested replacing the rewrite harness with Terminus-2. Implementation:
`agentic/src/append_rewrite/terminus/`. Protocol and admission:
`agentic/docs/terminus-rewrite.md`. Data-source research:
`agentic/docs/agent-data-sources-20261102.md`.

Old Claude Code paired trials, original paper scripts, frozen sources and original
scores are preserved. No model replay or new API inference is part of this change.
Native integration is scripted against the installed pinned Harbor and isolated
tmux on MindLab. Capability hold: candidate/input logprob scoring. Environment
hold: portable arbitrary tmux/process snapshot adapter. These are not hidden by a
protocol rename. A first new live provider trial needs its own frozen admission.
