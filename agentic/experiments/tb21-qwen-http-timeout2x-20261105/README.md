# HTTP Qwen base TB2.1, agent timeout ×2

User authorized a new89-task Pass@1 cohort on2026-11-05. Reuse the self-hosted
`Qwen/Qwen3.8-27B`, HTTP `http://123.57.26.97:8000/v1`, through the existing
ECS loopback18133 byte-preserving bridge. No SSH tunnel to the model service,
Fleet model switch, new deployment or training request.

Only agent.timeout_sec is doubled independently in each copied task.toml:
900→1800,1200→2400, etc. Job timeout_multiplier remains1, so verifier and setup
timeouts are unchanged. Original task configs/results and all SFT clients stay
untouched. Copied task payloads are hash-bound; task.toml atomic replacement
breaks its hardlink before changing the agent field.

All89 official tasks remain selected, commit7131e4375048a0e408a8fb404b5f499d726b695b;
Harbor0.23/Terminus-2, Alibaba Sandbox, temperature.6, pinned native input_ids,
context262144/output128000, public JSON action protocol, no turn cap and original
summarization settings remain unchanged. One fix-git canary is reused within
this new89-trial cohort; then88tasks at4concurrent. No automatic paid replay.
Full-check binary success, valid failure and execution/unknown outcomes remain
separate; a timeout's diagnostic reward0 is not a valid completed model0.

Reusable execution is the committed paired-SFT ecs_eval.py controller, frozen
into this batch's runtime; prepare.py performs only config derivation and launch.
Binding, task-manifest, timeout-changes, launch intent and process identity are
written before/at dispatch. Credentials stay in an own0600 native config and
the existing HTTP bridge, never public configs or Git.

ECS root: `/mnt/ecs-tb4/evaluations/qwen38-http-base-timeout2x-20261105-a1`.
This is a new increased-time cohort, not a replacement of the original or a
best-of-retries score. Report HTTP×2 separately from original1× and Fleet1×.
SFT training and its previously configured evaluation stages are not modified.
