# Expert-conditioned append rollout

Research extension of the original text-only sampling project. The initial
experiment is **one complete append task per sample**, not one tool call and not
the consolidated cold single-step. No training or MCMC claim is made here.


## Selected protocol: native Claude Code (2026-11-02)

New paired studies use the same pinned Claude Code 2.1.207 binary and Harbor
ClaudeCode implementation for DeepSeek and Qwen. `claude_agent.UnifiedClaudeCode`
reuses the frozen tb4-foundry `OfflineClaudeCode` adapter. The former OpenAI
`execute` loop in `run.py` is retained only as a historical harness.

`claude_protocol` imports a mainline, observable-only native JSONL with a new,
source-bound session ID. Hidden thinking/signatures are removed; original role,
tool-use IDs, feedback and public text are retained. The CLI loads this file via
native `load`/`--resume`; the historical transcript is no longer a user JSON blob.
The current expert reference, when present, is a tagged section of the new user
instruction. Both models use this same derived public-import protocol; old expert
runs with opaque original native state remain historical evidence.

The real pinned CLI and shared Harbor agent passed four deterministic loopback
provider cases (DeepSeek/Qwen x reference/no-reference), including restoration of
49 historical tool pairs and an actual Bash execution/feedback round. These checks
use zero model generations and do not test real provider inference compatibility.
Prepared profiles and admission receipts live in external study storage.

Compacted histories, sidechains, unbound images or unknown native project keys
require explicit adapters; preparation fails closed. Never flatten them silently.
Native Bash timeout uses milliseconds, as defined by Claude Code. Requested CLI
context/output hints must still be checked against each provider's capacities.

```sh
python -m append_rewrite.claude_protocol --inventory EXTERNAL_INVENTORY \
  --sample SAMPLE_ID --qwen-model SERVED_ALIAS --output NEW_PROTOCOL_DIR
# Uses an operator-pinned shared tb4-foundry source snapshot on PYTHONPATH:
python -m append_rewrite.claude_preflight --prepared NEW_PROTOCOL_DIR \
  --sandbox-credentials PRIVATE_SDK_ENV --output NEW_OFFLINE_CHECK_DIR
```

The prepared protocol has live inference disabled. A later provider compatibility
probe and new reference/no-reference experiment need explicit selection. The
legacy Qwen scores cannot be mixed with native-CLI scores as one protocol.

## Data

`append_rewrite.collect` indexes existing DeepSeek continuation receipts, checks
original successful termination and source identities, and separates the actual
parent observable context from the newly generated expert continuation. Native
thinking/signatures are omitted. A sample binds:

- public historical context, with URI and SHA256;
- frozen public file state at append start, bytes/modes and restore location;
- this append's public instruction;
- observable successful expert actions and real observations;
- original receipt, outcome, native source identities and scoring provenance.

Files stay in external private storage. `source_indexed` is not runtime admission.
Missing parent sessions, unsupported service-state restoration and post-hoc score
corrections remain explicit holds. No old model attempts are repeated.

## Historical custom-harness execution

`append_rewrite.run` restores an owned network-restricted cloud sandbox and runs
Qwen through Fleet from the controller. The model calls `execute`; each feedback
message is obtained from the real tool run. The sandbox receives no Fleet or cloud
administrative credential. The published expert behavior is reference material,
not a source of fabricated current observations. This is a new OpenAI-tools
harness, not a claim of native Claude Code parity.

Before a student attempt, run `--mode expert-control` and `--mode initial-control`
against the same task/template: original expert must pass, initial state must
fail. Student output is captured and independently restored/scored. Original
failures, HTTP errors, incomplete generations and costs remain in receipts;
there are no automatic model retries. Each output directory is exclusive.

Use the module with `PYTHONPATH=agentic/src` and an operator-configured SDK env:

```sh
python -m append_rewrite.collect --output EXTERNAL_CORPUS
python -m append_rewrite.run --inventory EXTERNAL_CORPUS/inventory.json \
  --sample SAMPLE_ID --fleet-config PRIVATE_FLEET_CONFIG \
  --sandbox-credentials PRIVATE_SANDBOX_ENV --output NEW_EXTERNAL_ATTEMPT
```

Controls use the same arguments with `--mode expert-control` or `initial-control`.
No credentials, raw expert native files, generated private reasoning, full captures
or task graders are committed. Generation input includes privileged expert
material; it is **not** an SFT example. Future exports must remove privileged
conditioning, mask repeated history/tool observations, and separately admit data.

## Engineering

Stable code belongs in `agentic/src/append_rewrite`, tests in `agentic/tests`.
Pin commits and SDK identities before rollout; run immutable source from external
persistent storage. Existing experiments/images/graders are read-only sources.
The upstream math/chemistry code and training behavior remain unchanged.

Model-free checks: `PYTHONPATH=agentic/src python -m unittest discover -s agentic/tests`.

Fleet inference uses durable Jobs: each generation records an exclusive intent,
then the accepted job ID, then terminal output. Interrupted result reads reconnect
to that ID; they never submit a replacement generation. Lost POST acknowledgement
is a hold. Completed jobs with incomplete generations remain a hold.

State extraction follows the original `runtime-binding.json` restore manifests.
A folder called `environment/public` does not establish its destination: some
lanes restore to `/app/project`, others to `/app`, and some restore multiple
roots. Every restored file must match an expected hash/mode, obtained only from
the published pre-append package or captured parent trial. Missing bindings,
multimodal assets and service-state adapters remain holds before student dispatch.


The initial study and completed whole-append pilot are documented in
[append-rewrite-pilot-20261102](experiments/append-rewrite-pilot-20261102/README.md).
Historical screenshot bytes are stored as hashed external assets. The text
controller explicitly holds multimodal samples rather than passing image paths
as if they were visual observations. `audio_state` reproduces the original audio
environment startup without solver calls and materializes a reusable state index.
`collect --receipt-inventory ... --state-adapters ...` fixes source membership
while incorporating those states. `catalog` groups equivalent append units.


A paired no-reference control uses `--reference-mode none --paired-reference
PATH_TO_COMPLETED_EXPERT_CONDITIONED_ATTEMPT`. It checks that the original
expert-conditioned input is reconstructed byte-for-byte and the requirement,
state manifest and verifier hashes match. It removes only the current append's
expert continuation section. Historical parent context and starting files remain
unchanged. This is a distinct experimental condition, not an automatic retry.


## Review-stage tool-boundary core

Branch `research/tool-boundary-rewrite` adds a model-free prototype in
`src/append_rewrite/tool_blocks/`. It segments complete tool batches, evaluates
fresh-state branches with their own observations, keeps expert reference separate
from student scoring, and exports continuous SFT-window previews. Read the
[design and remaining native integrations](docs/tool-boundary-rewrite.md). This
does not change the selected production harness or run new models.
