# Tool-boundary rewrite review

Purpose: implement complete tool-interaction boundaries, checkpoint/fork identity,
actual per-branch feedback and continuous SFT-window previews before connecting
new paid model runs. Review code in [the design](../../docs/tool-boundary-rewrite.md).

The executable offline demo uses real isolated file directories and explicitly
fake likelihood scores. It must reject the higher-scored wrong candidate and
read the selected branch's own result. It creates no model/cloud requests.

The Coq data check is read-only cataloging of existing public expert/context and
student logs on MindLab. It does not reconstruct missing per-tool historical
snapshots, replay tools, rerun grading or query a model. Detailed source-bound
catalogs and review results belong in persistent external study storage.

Acceptance: test malformed/partial/parallel feedback; state drift and corruption;
foreign receipts; alternate action/observation divergence; reference separation;
local contract gates; lineage integrity and contiguous message loss masks. Keep
all exported examples `training_admitted=false`. Native CC boundary pausing,
full environment snapshot adapters and real logprob scoring remain explicit
integration tasks for a later reviewed experiment.

## Read-only acceptance observed

Frozen implementation2760a9e passed the file-fork demo both locally and on
MindLab. The existing Coq append3 public traces also match native CLI counts:

| Existing continuation | Interaction blocks | Tool calls | New execution |
|---|---:|---:|---|
| DeepSeek expert | 11 (10 exchanges + final reply) | 10 | None |
| Qwen no-reference student | 23 (22 exchanges + final reply) | 22 | None |

The115-message shared prefix is context, not counted as this continuation.
Neither historical catalog claims to have per-tool environment snapshots.
External evidence is under `data/tool-boundary-review-v1/` in the existing
projection-agent study root; no real trajectory contents are committed here.

Agentic regression suite:53pass, including24new boundary/branch/SFT checks;
Ruff and diff whitespace checks pass. Fixture scores are not model logprobs.
The review stage is ready for source review, not production rollout/training.
