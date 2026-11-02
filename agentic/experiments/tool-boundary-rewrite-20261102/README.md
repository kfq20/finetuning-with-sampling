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
