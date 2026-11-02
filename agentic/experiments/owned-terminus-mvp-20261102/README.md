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

## Teacher accepted; student dispatched

Fresh DeepSeek teacher completed 29 native model decisions / 46 shell commands.
Original reward1 and independent restored reward1. Coq compilation, all nine
closed-assumption checks and coqchk passed. No private grader/solution path hits
were found in observable commands. Review: selected teacher root/TEACHER-REVIEW.json.
Teacher receipt SHA256:
`991e2e4d4645624f200fc9a9b6cf800d2cb2b460017cb7b3df4724cce8a6eb8a`.
Teacher history SHA256:
`7e540b9a3d9bd27e43ef76d6bfbe38db161c61527525c48a5446888ed2912033`.

One Qwen student now selected at `data/owned-terminus-coq-qwen-mvp-v1`; launch
identity in the adjacent `-launch.json`. Frozen source:
`source-owned-terminus-student-v3`, commit `46cea8a`.
Entry: `python -m append_rewrite.terminus.owned_student`.
Tokenizer: `tokenizers/qwen38-27b-1d4bf0f`.
No old student attempts are replayed. Exact served deployment identity was
rechecked. First native generation is an actual provider request, not a configured
claim. Later outcome is authoritative only in receipt.json or error.json.

Model-free checks additionally verified candidate ranking with reference only in
generation, actual pinned-HF template SFT masking, and teacher SSE privacy/closure.
Final dataset export includes token IDs and assistant-only labels; reference is
not in public messages. Original/fresh semantic success is required for export.

## Student parser recovery (no completed model generation repeated)

The first student executed its initial read-only decision and generated four
candidates. Both turn-2 candidates had public prose before valid JSON. Harbor
accepted them, but our strict validator rejected them. This is a protocol error,
not model failure or provider error. Raw generations, scores and original error
remain immutable. The parser now accepts the same public JSON surroundings while
preserving exact raw candidate bytes for likelihood and training. Hidden thinking
wrappers remain excluded.

Selected continuation: `data/owned-terminus-coq-qwen-mvp-recovery-v1`, frozen source
`source-owned-terminus-student-v4`, commit `9f5c17a`. This is a narrow recovery
after only cat/ls commands: original project hashes/modes restored and verified;
no arbitrary process snapshot claim. Actual historical observations are retained
as history, not manufactured as new feedback. Both cached candidates' complete
generation input token sequences matched the reconstructed prefix. They were
rescored and one executed; no old generation was repeated. Later requests are
new continuation decisions. `recovery-binding.json` and the original run's
`RECOVERY-PREFLIGHT.json` bind evidence. Prior usage/cost remains charged once.
