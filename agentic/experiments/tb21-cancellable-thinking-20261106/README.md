# Qwen TB2.1: cancellable thinking canary

This opt-in benchmark profile uses a cancellable async HTTP/SSE request instead
of a synchronous request inside `asyncio.to_thread`. Existing generation/scoring
and frozen benchmark runs keep their prior profiles and identities.

Official reference: https://huggingface.co/Qwen/Qwen3.8-27B (checked 2026-11-06).
Thinking on, preserved reasoning history, xhigh; temperature1, top_p.95, top_k20,
min_p0, presence_penalty0, repetition_penalty1. The parser sends only final
content to the Terminus command parser; native reasoning remains private and is
retained in history. Reports expose counts/usage, never raw reasoning.

Cancellation exits the HTTP stream context before returning, with no surviving
inference thread. The optional SGLang scoped abort sends only our own rid and
`abort_all:false`. The current user-authorized direct router returns404 for
`/abort_request`; its canary uses socket closure, and server compute termination
is explicitly unconfirmed. No client response can be written after cancellation.
No retries, fallback, or global abort are introduced.

## Experiment

Selected ECS root:
`/mnt/ecs-tb4/evaluations/qwen38-cancellable-thinking-canary-20261106-a1`.
Each of regex-log/password-recovery/polyglot-rust-c runs once, concurrency3,
using the exact task files and per-task doubled agent deadlines from the prior
HTTP base cohort. The model remains the same direct HTTP Qwen base. Existing
results, training runs and active experiments are not modified.

This is a three-task historical comparison of repaired transport + thinking +
sampling; it cannot isolate any one change or reproduce the unpublished complete
protocol behind the official73% result. Serving context262144/output128000
remain explicit constraints. No automatic retry or full-benchmark continuation.

`run.py prepare ROOT` creates the private credential/config and old-result hash
bindings on ECS. `run.py run ROOT` has an exclusive lock and one dispatch claim;
`collect ROOT` is read-only except replacing the current progress snapshot.
Frozen code hashes and prior task/result hashes are checked before dispatch.
All infrastructure errors remain unknown rather than valid model0.

## Checks

- Existing native SSE strict stop/identity/length controls.
- Local socket cancellation before response headers and during partial SSE.
- Scoped abort identity and failed/unavailable abort reporting.
- Native thinking/content separation and incomplete-thinking rejection.
- Actual installed Harbor response/history compatibility (ECS preflight).

## 2026-11-06 result

Three first canaries (frozen2291c07) ended: polyglot-rust-c normal reward1,
4 completed calls/16.46min; regex-log24 and password-recovery5 completed calls,
both1800s AgentTimeout. Timeouts are unknown outcomes, not valid model0.
No retries or full-batch dispatch followed.

Followupfd34619 keeps inference journals outside agent sandbox uploads and
records lossless text deltas; buffered SSE has an explicit scheduling checkpoint.
Actual ECS26 regressions pass. A short real endpoint cancellation returned in
0.000441s, with no late response97s later. These followups were not retroactively
attributed to the original three paid canaries. The public abort route is404;
operator SSH control of exactly three owned expired/probe IDs returned200 from
internal8131 with abort_all=false. Automatic ECS remote abort remains unbound.

Full metadata/evidence report (external data, not raw reasoning):
`/Users/fancy/project/finetuning-with-sampling-data/tb21-cancellable-thinking-20261106/REVIEW.md`.
Native cumulative SSE still creates quadratic network traffic; local incremental
logging does not fix that transport. The password first call reported20.12s
server e2e versus847.59s client time. Further timing isolation and incremental
transport should precede a full evaluation rerun.
