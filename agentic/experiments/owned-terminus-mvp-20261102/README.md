# Owned environment: fresh Terminus teacher → student rewrite MVP

User redirected the MVP from OpenThoughts back to our existing environments.
Public SFT records alone do not establish interactive feedback or restorable
states. No OpenThoughts student rollout was launched. Its acquisition/audit data
remains external and unselected.

Use the existing Coq append-3 unit `c110ddbf8085c8e05cb3`: preserve eight established
list-partition theorems and prove `partition_count_occ`; original private verifier
checks nine closed proofs, compilation and coqchk. Source requirement, initial
project, task and grader are frozen into the new study before dispatch.

New DeepSeek-flash expert uses native Harbor Terminus-2. Old CC context/answers
are not imported. Same native harness will be used for Qwen. This is a fresh
harness experiment over the existing append checkpoint, not a replay of the old
paid attempt or a claim of identical CC history conditioning.

External root:
`/vePFS-Mindverse/user/intern/fanqi/tb4-research/projection-agent-20261102`.
Selected launch: `data/owned-terminus-coq-mvp-v2-launch.json`.
Selected run: `data/owned-terminus-coq-mvp-v2`.
Frozen source: `source-owned-terminus-mvp-v2` (implementation commit `f9f82fa`).
Entry: `python -m append_rewrite.terminus.owned_mvp`.
Runtime assets: `runtime-assets/tmux-linux-x86_64-v1/manifest.json`.

Initial v1 environment controls were 0/1; it stopped before the first model
request because the old Coq image lacked tmux. V1 is retained as an unpaid runtime
failure. V2 applies a hash-bound offline tmux/shared-library/terminfo layer only
inside owned sandboxes, with actual session smoke. Original task, verifier and
shared image are unchanged. No apt/pip fallback or shared daemon changes.

Teacher must close native completion normally, capture the real Submission.v,
and score 1 both originally and in an independent restored sandbox. Only then is
the new expert admitted as MVP reference. Endpoint/model/credential digest match
the existing user-approved DeepSeek policy; private reasoning and keys are not
exported. No automatic paid retry or endpoint/model fallback.

Student integration uses the same local Qwen tokenizer/template for native
`/generate` generation and forced candidate scoring. Initial real scorer check
matched all input IDs; generation-side checks remain per-request. Candidate
selection is explicitly a greedy blockwise MVP, not full MH/MCMC. Real terminal
feedback is required at every step; only actually successful, independently
restored outputs can become SFT candidates.
