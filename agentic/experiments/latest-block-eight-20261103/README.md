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
