# Expert-conditioned append rollout

Research extension of the original text-only sampling project. The initial
experiment is **one complete append task per sample**, not one tool call and not
the consolidated cold single-step. No training or MCMC claim is made here.

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

## Execution

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
