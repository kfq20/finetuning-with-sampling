# Paired531 Fleet timeout recovery, original agent time ×4

User explicitly selected Fleet base/method-SFT/expert-SFT and one retry of each
original AgentTimeout on2026-11-06. Fixed original counts:41/42/39 =122 trials.
No successful/valid-zero/API/install/capture error task is eligible for replay.
This is a recovery protocol, not a new all89-tasks-at4x result or best-of2 score.

Each selected task copies the original package; only agent.timeout_sec is4x
(900→3600,1200→4800). Global multiplier1; setup/verifier budgets unchanged.
Original model IDs, final step34 adapters, Fleet endpoints, tokenizer/template,
JSON parser, temperature.6, nonthinking, context262144/output128000, summaries,
no max_turns and all other agent/environment options remain unchanged.

Previously approved safety fixes remain: cancellable async streams, scheduling
checkpoints, controller-only inference journals and lossless delta capture.
No new top_p/top_k/reasoning-effort setting or fallback is added to inference.
Preflight verifies token-ID rendering equality against the frozen original
renderer,26 common regressions +4 recovery tests, actual deployed checkpoints
and a small nonthinking native SSE probe per model before any task dispatch.
Fleet's actual current placement is recorded rather than silently redeployed.

ECS root:
`/mnt/ecs-tb4/evaluations/qwen38-paired531-timeout4x-retry1-20261106-a1`.
`run.py prepare ROOT`, `preflight ROOT`, then `controller ROOT` are sequential.
One controller owns three Harbor jobs,4concurrent trials each (12maximum total),
with max_retries0 and a persistent dispatch claim. All sources/configs/task files
and parent timeout results are SHA-bound before launch. Never reset a claim or
rerun this controller to repeat a paid attempt.

Progress distinguishes finite normal grades, full-check success and errors.
A timeout's raw reward0 stays diagnostic/unknown. Original results, checkpoints,
failures and costs are preserved. Subsequent reporting must identify adaptive
1x→4x recovery and keep the self-hosted HTTP/thinking canaries separate.
