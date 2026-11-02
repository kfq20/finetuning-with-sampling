# Owned environment: fresh Terminus teacher → student rewrite MVP

**Final selected run:** `data/owned-coq-block-mvp-v2`. Technical block MVP passed.
Two student proposals passed original + independent restored verification (1/1
each). One masked SFT row exported: 33,846 tokens / 382 supervised tokens.
Delivery: `data/owned-coq-block-mvp-delivery-v1`. Prior free-rollout roots below
are preserved history, not selected or running.

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

## Final grounded block MVP

Free continuous rollout exposed a method defect: selecting syntactically valid
high-mean-LP actions without feasibility/progress admission repeatedly selected
identical reads. It was intentionally stopped via SIGINT; its in-flight response
was allowed to finish and all old responses/usage were preserved. This is not
labelled a Coq model failure.

The final MVP uses the originally discussed one-tool-batch unit: replay the first
24 expert tool decisions into an owned sandbox (zero expert model replay), freeze
its actual files and quiescent shell scope, then rewrite expert decision25.
Each candidate forks that checkpoint, executes through native Terminus, and runs
the original later delivery tools with its OWN real observations. Original and
fresh verifier success are required BEFORE likelihood-based selection. Teacher
future observations are never substituted for new observations.

Controls: initial0; original expert block1/fresh1; no-op replacement0/fresh0. The
first prepared block run stopped unpaid on an incomplete no-op response schema;
its checkpoint and successful expert control were reused by source/hash binding.
Final frozen implementation: `source-owned-block-mvp-v2`, commit `82d9646`.

| Action | Tokens | Mean student logprob, no current expert reference | Original / fresh |
|---|---:|---:|---|
| Original expert block | 413 | -0.272218 | 1 / 1 |
| Student candidate0 | 418 | -0.265378 | 1 / 1 |
| Student candidate1, selected | 381 | -0.248373 | 1 / 1 |

The training row supervises ONLY selected student block1 (381 raw action tokens
plus one end-of-turn token). All 49 teacher-prefix messages are context and fully
masked. Native forced-score input IDs exactly equal the matching SFT input prefix;
candidate start equals the first loss position. No current expert-reference
prompt or private provider reasoning is exported. The selected action has no
dangling attribution to an unseen expert/reference.

The final Submission.v is byte-identical to the expert's: this proves compatible
proof repair, not new independent mathematical discovery. The selected action is
a replacement inside an expert prefix/suffix, not an autonomous full student
episode. This is executable greedy block rewrite; full MH proposal/acceptance
correction and learning-benefit/no-reference studies remain separate research.

`FINAL-REVIEW.json`, `receipt.json`, `baseline-expert-score/score.json` and both
candidate verdicts bind raw outcomes. The complete technical block run took
481.665 seconds, excluding earlier preserved prototype failures/preparation.
No model training or rollout scale-up was launched.

Validate the delivery without model requests:

```sh
PYTHONPATH=agentic/src python -m append_rewrite.terminus.validate \
  /persistent/owned-coq-block-mvp-delivery-v1/train.jsonl
```
