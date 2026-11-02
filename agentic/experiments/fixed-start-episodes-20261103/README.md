# Fixed-start multi-step rewrite pilot

Use one existing successful Coq append3 unit, frozen by the admitted Terminus
teacher in owned-terminus-coq-mvp-v2. The complete public expert history is
reference conditioning, never synthetic student feedback. Starting project and
output reset are identical across fresh independent student candidates.

User authorized one unit first, then expansion after verified closure. Stage A
runs one full-reference Qwen3.8-27B episode, native Terminus-2, one sample per
decision. No action-level likelihood ranking or teacher suffix replay. Normal
completion and original/fresh reward1 precede offline no-reference policy scoring
and masked SFT export. A legitimate normal zero remains a valid unsuccessful
candidate, not infrastructure failure. Errors remain errors, no automatic retry.

After review of Stage A, add an independent full-reference candidate and an
unreferenced comparison on the SAME unit. Successful reference candidates are
ranked by token-weighted mean policy logprob over assistant action text only,
conditioned on their own real histories. Public actions include the native plan
fields; provider-private thinking is excluded. Candidate EOS is supervised by
SFT but not included in the current likelihood statistic. Teacher content is
removed from the extra conditioning in scoring and from exported messages.

No arbitrary checkpoint rollback/random cuts, iterative accepted-prefix chain,
or exact MH implementation is claimed. Full reference can disclose the final
solution: copy similarity is measured, and reference success alone is not a
learning-benefit claim. Batch admission requires task/state/grader identities and
recovery adapters, not merely historical rollout counts.

Sources in Git; immutable source archive and private credentials stay under the
existing external projection-agent-20261102 research root. No changes to prior
runs, original append workers, shared runtime or shared skills.

## First full episode passed; comparison and small expansion

Selected first episode: external `data/fixed-start-coq-reference-01`.
Runtime commit `2a91002`; `receipt.json` and `QUALITY-REVIEW.json` bind result.
10 native decisions / 21 shell commands, all 10 API responses complete, zero
recorded API errors. Rollout 656.10s; capture + original/fresh grading 66.02s;
unreferenced forced scoring 51.37s; total 791.09s. Both rewards1.
Generation input peak 49,616 tokens including the full expert reference.
SFT: 11,168 total tokens / 2,549 supervised; public prompts/observations masked.
Action likelihood: 2,539 action-text tokens, mean -0.288037823 (EOS excluded).
The extra 10 supervised EOS tokens explain the count difference.

The final proof artifact exactly matches the expert. This is a reference-assisted
rewrite success, not evidence of independent proof invention. Reference candidate2
and a no-reference episode use independent starting sandboxes and identical task,
state, tokenizer, native harness, temperature and token limits. No old attempts
were repeated. They run under the unchanged first frozen source.

Next small expansion selects existing Coq append4 and append5 from corpus-v5.
`append_rewrite.terminus.unit` runs a new DeepSeek native teacher with original0/
legal1 controls, original/fresh success, then one full-reference Qwen episode.
Each exclusive unit stops on an error; completed steps and costs stay preserved.
It uses the same Submission.v state/artifact adapter, not a claim that the other
domain state adapters are already generalized. Source inventory:125 rows,
105 original positives,104 deduplicated positive units at this frozen cutoff.
No-reference comparison is not an upstream gate for manufacturing new experts;
it is required to evaluate reference usefulness before a training-effect claim.
