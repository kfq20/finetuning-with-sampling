# Saved sampler pending: 2026-11-05 diagnosis

The client transport/registration path works; generation is not yet usable.
No training was replayed and no production worker/configuration was changed.

## Observed evidence

- New independent SDK comparison, using the original saved sampler artifact:
  base `Qwen/Qwen3.8-27B` and saved LoRA each registered successfully and received
  HTTP200 async future handles. Both stayed pending in the observation window.
- HTTP response tracing shows actual REST `retrieve_future` HTTP408 responses,
  `queue_state=active`, `status=pending`. Server client-config disables gRPC and
  pyqwest, so this is not a gRPC-only result-reading failure.
- Current server source explicitly maps non-training-creation pending requests to
  `active`; this label alone is not GPU execution/engine readiness evidence.
- Authenticated MintStatus Grafana, environment `prd`, metric
  `mint.scheduler.composers.connected`, series `sampler`: **721/721 samples are0**
  from 2026-11-05 10:13:30 through16:13:30 Asia/Shanghai. CSV SHA256
  `ec35974cc264ef255c72d3a6b01e26d90be583790dc8f759f1574d2cf0059bcc`.
  This is aggregate production control-plane evidence, not a per-task startup
  traceback or proof of the exact API-to-scheduler route.
- The original one-step state loaded with optimizer and ran finite forward.
  Checkpoint storage contains both state and sampler after resource cleanup.

The strongest diagnosis is unavailable/disconnected production sampler execution,
consistent with base and LoRA both pending. The exact cause of engine startup or
registration failure is not established. Do not claim an SDK creation fix or a
successful generation. Old GitHub issues1675/1784 are historical leads only;
current source already has vLLM sampler startup wiring.

## Access boundary

The business token returns401 on management task-detail routes. Logs/traces/metrics
MCP authenticated POSTs return503, including through the local network relay.
An unauthenticated GET returning401 is a different request and does not establish
that the earlier503 is a MindLab network issue. The current MintStatus account has
no active machine grant. No management key was sought to override the rejection.

The administrator needs to verify the scheduler serving `mintcn.../train`, inspect
these exact tasks and the Qwen3.8 sampler composer startup/registration, then
recover only that sampler. Preserve trainers and other experiments. After ready,
run base1token, then reload the existing saved sampler and run1token; no training
is needed. If no task claim/start exists, inspect routing/engine availability;
otherwise inspect the owning worker's initialization and adapter-load logs.

## Identities and retained receipts

- Original sampler future: `01a1aa9f-8486-7712-b43d-1dca9b0033b8`.
- New base future: `01a1aab2-3f54-742a-96c9-b30d74a925a8`.
- New saved-checkpoint future: `01a1aab2-3fd5-7008-b3ea-2f23571b3c3c`.
- New comparison session: `01a1aab2-3e27-72aa-a2e3-430e5bef0cfa`, now closed;
  its two sampler resources are deleted, with no training client created.
- Evidence root:
  `/Users/fancy/project/finetuning-with-sampling-data/sampler-diagnosis-20261105-a1`.
- Original training/checkpoints:
  `/Users/fancy/project/finetuning-with-sampling-data/mint-sdk-one-step-20261105-a1`.

## Client changes for future runs

The isolated comparison records request/future IDs and pending responses, waits
for a finite observation window and cleans up only its own session. The one-step
acceptance source now labels the metadata operation `register_sampler`, not
`load_sampler`, and requires an explicit positive `smoke.wait_timeout_seconds`
before it can create resources. That timer applies only to sampler readiness
observation, not benchmark generation. Old frozen workers/parameters and failures
remain unchanged; creation success is never a generation-readiness admission.
