# Expert-conditioned whole-append feasibility study

The experimental unit is a complete previously successful DeepSeek append:
starting public history + bound file state + new requirement + observable expert
continuation. Qwen executes its own commands against a restored sandbox and
receives actual tool feedback. Upstream math/chemistry training code is unchanged.

Execution stages:

1. Index original successful native continuation receipts and verify the source
   result, parent prefix, successful continuation and scoring identities.
2. Restore files to the original published destinations using hashes/modes from
   checkpoint manifests and the captured parent trial. Missing state or images
   require an adapter; no guessed destination or fabricated observation.
3. Group equivalent context/state/requirement units, preserving every source receipt.
4. Require original expert submission=1 and unmodified starting state=0 in the
   target sandbox before calling the student.
5. Give Qwen the observable expert as privileged reference; generate a whole
   append with real execute feedback. Tool argument errors are feedback, not an
   automatic trajectory abort. Private grader is mounted after student termination.
6. Capture the submission; restore its exact bytes/modes in a second sandbox;
   score independently and bind both scores. Model zero is distinct from API,
   incomplete-generation and capture failures.

The selected frozen catalog contains125 source receipts. All105 original normal
full-success records have context, requirement, observable expert continuation and
bound starting files; they represent104 unique append units. Three include bound
historical screenshots and require a multimodal student execution adapter.
Eighteen audio records include original-template startup snapshots. Twenty other
records require outcome-specific derived review before positive admission.
Source indexing does not imply sandbox or training admission.

Integration checks established complete Chat SSE with parsed Qwen tool calls.
Fleet Jobs rejected the very model alias that its deployment and models endpoint
advertised; those submissions were not accepted generations. Jobs support remains
available in code, but this study explicitly selects Chat SSE for its deployment.
There is no automatic paid retry or silent transport switch within an attempt.

The first Bio trial completed 12 generations and 11 actual tool calls before the
old harness rejected a milliseconds-valued timeout. The original record is
preserved unscored; it is not evidence of task failure. The revised harness reports
schema errors back to the student and saves partial state on exceptional exit.
The corrected Coq append3 completed: original expert control1, initial0, Qwen1,
fresh-restored1. Seven API rounds and seven real tool calls, 2.66 agent minutes
(3.68 total minutes), peak input55,496 tokens, cumulative input367,651 tokens,
output2,519 tokens. The single submitted source artifact retained identical bytes
and modes after fresh restoration. Observable commands used no private grader
paths. This is one feasibility result, not a success-rate or training-gain claim.

Execution, credentials, corpora and trajectories remain in private persistent
storage, outside Git. Each attempt pins its code commit and uses an exclusive
output directory. No original DeepSeek attempts were replayed. This study does
not run SFT or MCMC; generated input with privileged reference is not training
admitted. Future training exports must remove that reference and mask conditioning
prefixes/tool observations according to their chosen objective.
