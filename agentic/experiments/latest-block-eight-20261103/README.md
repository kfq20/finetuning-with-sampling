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

## Matched three-arm qualitative comparison

User authorized one no-reference eight-candidate episode, then one complete
full-reference DIRECT episode. Both use the same task/start files/native parser,
tokenizer,temperature0.6,128000 output cap and native SSE transport as the original
eight-candidate episode. The direct arm uses `--algorithm full-episode-stream`:
one generation per interaction, no online score/selection. Forced action likelihood
is calculated only after the full episode, including normal zero outcomes; final
verifier is evaluation and successful SFT export remains separate.

No-reference eight-candidate arm runs independently on frozen835892f; it is not
restarted or altered by the new direct arm. Historical nonstream direct results
are preserved, but do not substitute for this matched transport comparison.
Actual starting terminal hostnames differ across owned sandboxes; task/state
bytes, native harness and parameters are bound identically. Stochastic draws are
independent. Single episodes support qualitative inspection, not success rates.

Compare: reference benefit (reference8 vs no-reference8) and selection effect
(reference8 vs reference-direct). Track final reward, action/command counts,
actual errors/repairs, repetition, output length, reference-copy similarity,
unreferenced action likelihood and wall time. Higher likelihood is a proxy for
student compatibility, not proof of learning benefit; that needs downstream
training and unreferenced held-out evaluation.

### Matched direct arm completed

Direct sourceeb5b3b7, data/direct-stream-coq-reference-01. Receipt SHA256
8217b9db93bceb84e0101352209abe264467b2a623dc323dfc209fdc0eeef542.
8 normal native responses/13 shell commands; original1/fresh1. Rollout191.833s;
total319.458s includes64.816s grading+50.000s POST-episode scoring.8generation
calls,8offline scoring calls; journal timestamps verify no online scoring.
Generation input342061/output1896; score input35229; unreferenced mean action
LP -0.320684 vs eight-arm -0.180634. Direct artifact exactly matches expert;
both arm artifacts match after removing whitespace. Direct had no feedback
blocks with Coq Error; eight-arm had two at3/4. Qualitatively direct is shorter
and cleaner here; higher likelihood does not itself demonstrate learning benefit.

New derived training-quality reviews hold BOTH exports: selected block2 refers
to unseen expert material after reference stripping. Original raw exports, scores
and prior technical-admission flags remain unchanged; TRAINING-QUALITY-REVIEW.json
is authoritative for current release approval=false. No clean SFT release made.

No-reference eight-arm completed23 selected blocks, generated all192candidates
through24;190 forced scores completed. Candidate4/7 of24 hit IncompleteRead
at31.249/31.260s on NONSTREAM zero-generation scoring. No action24 executed.
All generation streams completed; failure is scoring transport, not model0.
Full files-only partial state retained (SHA256
0fbf5632aa4d72206a31ae5032e2ac656968111c820080a6431668a7f6b450f1).
No automatic retry/regeneration/restart. All current owned workers exited.
Comparison delivery: data/three-arm-coq-comparison-v1, includes both observable
histories, receipts, quality holds and explicit no-reference transport status.

## User clarification: plain no-reference baseline (selected next)

The intended no-reference comparator is ONE generation per interaction, no expert
reference and NO candidate pool/logprob choice. The earlier no-reference8 arm was
a coordinator misunderstanding; it remains separate historical evidence. Planned
8-arm rerun was NOT launched. Suffix-score calibration is unselected research
(9completed zero-generation requests, no solver generations); it does not gate
or enter this plain baseline.

New entry uses `--mode no-reference --algorithm full-episode-stream
--plain-baseline`: same Qwen/native Terminus/task/state/temperature/output limits
as the successful direct-reference arm; one real action followed by real tool
feedback. No online OR offline probability scoring, no SFT export. Final original
and independently restored verifier evaluate the result. A fresh source snapshot
owns the new attempt; old attempts/errors/costs stay unchanged.

## User-approved pure-baseline early stop and final three-setting comparison

User approved stopping the persistent proof loop and marking early termination.
Exact703754/start1892694749 was verified and SIGINT delivered at1793678931.567660.
Worker exited;71executed assistant turns/105shell entries saved. In-flight72
returned normally but never executed; all72responses/costs remain retained.
No new model calls for stop/review. Source aadbb06 unchanged, review fd162b2.

Full current-state capture restored with identical file bytes/modes; verifier0.
Separately restore only currentSubmission.v over frozen original input: verifier0.
Both fail actualCoq compilation atSubmission.v:115, Cannot find witness.
Operator receipt71af387f0008eb2d0fbe286a5f16f32adbf7cc1ec9c2e3b07388ce1f5ae5c668.
Status operator_stopped_early/normal_completed=false, not a normal model-zero.
Source captures b0aa4d2137ce08582d0d798b27340af624dc2abd666a6ecf05e980d5c7302dd9
(state) and3e0d1694a2b61109e23d57797524240769daf9b00c55e8ce657b50d54db286a6
(submission) preserved. Final selection THREE_SETTING_FINAL_SELECTION.json.

| Metric | Reference+8selection | Directreference | Pure no-reference |
|---|---:|---:|---:|
| State | normal | normal | earlystop |
| Verifier | 1/1 | 1/1 | currentcapture0/0 |
| Executedturns | 12 | 8 | 71 |
| Shellentries | 24 | 13 | 105 |
| Agentminutes | 7.2777 | 3.1972 | 49.4665 |
| Generationrequests | 96 | 8 | 72(1unexecuted) |
| Score requests | 96online | 8postepisode | 0 |
| Peak generation input | 49376 | 44736 | 89274 |
| Allinputinclhistory/cache(gen+score) | 4898368 | 377290 | 3251870 |
| Generationoutputtokens | 20288 | 1896 | 35476 |

All use the same inputmanifest e6491cd1abb9eaef76a85063e48d71c0b359d03efd6e829facd4682805dc1e19.
Input sums are not billing estimates. Context peak in reference arms includes
privileged expert reference. Review/data sources in data/three-setting-final-v1
and matching local external data. No prior failed no-reference8 results are
substituted for pure baseline. No skills/training changed or model replay made.
