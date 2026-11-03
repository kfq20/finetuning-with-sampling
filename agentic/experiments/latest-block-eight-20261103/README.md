# Latest-block eight-candidate append pilot

User-selected method: one Coq append3 task from its original frozen nonempty
starting state. Complete admitted native DeepSeek expert trajectory is privileged
reference. Qwen uses native Terminus-2. Each assistant command batch is one block.

At each public prefix generate eight independent candidates (temperature0.6,
128000 output limit), force-score raw assistant tokens without the extra expert
reference, choose highest mean logprob, execute ONLY that candidate, observe real
terminal feedback, continue. Native action syntax validation is the only candidate
admission check. No progress, repetition, expert-score or intermediate verifier
filter. No random cut, state rewind, teacher-tool replay or likelihood acceptance
against an incumbent. All eight candidates and scores are retained. An incomplete
pool is a transport hold, not a lower-count selection or implicit regeneration.

Native generation uses stream=true and explicit pinned input_ids; it requires
normal engine stop, consistent cumulative text/request identity/input length.
Only the first real candidate is initially requested to validate compatibility;
its output counts as candidate0. The remaining seven then run independently.
Later blocks fan out eight candidates. Scoring retains native input-logprob ID
verification. No automatic retries/fallback. First bytes, request IDs, raw events
and termination evidence are saved. Prior nonstream errors remain unchanged.
Native API contract: https://github.com/sgl-project/sglang/blob/main/docs/docs/basic_usage/sampling_params.mdx

The final verifier is evaluation only, after native task completion, and does not
influence block selection. Missing submission after normal completion is evaluated
as an empty submission, not misclassified as transport failure. Success-only SFT
export is separate from experimental outcome retention. Only one new episode is
authorized for this pilot; old paid attempts and other append workers stay intact.

Entry:
python -m append_rewrite.terminus.episode --algorithm latest-block-8 --mode reference
plus the standard teacher/tokenizer/private credentials/assets/output paths.

## Completed single-append result

Frozen runtime835892f, offline audit7f1a6fe. External research root
`projection-agent-20261102/data/latest-block-eight-coq-01`.
Receipt SHA256 `039231d3dae3174c68c6c6f1ff0b795c1ea459732d8c9ed7ae02b5b8e37c5191`.

12 blocks (including two native completion confirmations),96 generated AND scored
candidates,24 executed shell commands. Every chosen action was verified against
its eight-candidate maximum and actual student history. Both final rewards1.
Rollout436.660s includes all candidate generation/forced scoring; total517.286s
includes setup and65.045s final capture/grading. No intermediate verifier, rollback,
API error or literal repeated nonempty command batch. Selected path encountered
missing Submission logical-path errors at3/4, compiled the prerequisite at5,
replaced Admitted at6, then compiled/checked/delivered and closed normally.

Generation input4,291,408 tokens (cache/billing not inferred), generation output
20,288; forced-score input606,960. Peak reference-conditioned input49,376 tokens.
SFT row10,927 total/2,764 supervised tokens; selected action text2,752+12EOS.
Final submission text similarity to expert99.8828%; no claim of independent
proof invention or measured training benefit. Delivery contains score tables,
all96 candidate command batches, selected actions with actual observations and
one masked SFT row. No provider-private reasoning or credentials exported.

Transport metric note: first_byte_sec in this frozen stream implementation starts
after response headers. Use whole rollout or candidate elapsed_sec for complete
network-inclusive time; do not interpret it as POST-to-first-byte latency.
All owned workers exited; no follow-up model/automation was started.
