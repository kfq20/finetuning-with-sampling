# CLI-Gym pilot — 2026-11-04

User authorized a small multi-project end-to-end trial after stopping TB4 data
acquisition. The old TB4 selection and USER_STOP markers remain stopped. No
author sessions, subagents or automations are introduced.

Selected official dataset revision:
`LiberCoders/CLI-Gym@552945c5aaf07d9715549a798c98ee13bb5b7f06`.
The HF datasets-server rows 0–99 and dataset metadata are frozen outside Git.
The dataset actually supplies `task_yaml`, not the README's `instruction` column.
Literal instruction bodies are extracted without adding hints or repair steps;
original YAML/recipes/scripts are retained, including malformed YAML indentation.

Preselected subsets: Scrapy rows1/15, ExceptionGroup rows16/87, MarkupSafe rows29/46.
No task is replaced based on a model outcome. Unbuildable recipes or initial
states already scoring one remain explicit pre-model holds, not solved tasks.

Pipeline: pin/pull original base image → build published fault recipe →
initial0/healthy-base1 controls → DeepSeek Flash expert under native Terminus-2 →
two independent final snapshot grades → Qwen full-reference eight-candidate
rewrite with reference-free mean-logprob ranking → same independent grades →
existing assistant-only SFT admission. No intermediate verifier selection or
generation retries are added. The original task's episode timeout applies;
there is no model-turn limit. Candidate generation respects Qwen's actual 262144
context capacity. Expert parameters and approved policy/route are unchanged.

MindLab controls this pilot; isolated Docker containers execute on a study-owned
ECS daemon (4 CPU/8GiB each), with its entire data root on the ECS data disk.
An authenticated private SSH socket tunnel connects the controller to that daemon.
The initial MindLab shared-Docker pull failed unpaid on backing-store exhaustion;
its preparation receipt is retained, and that shared daemon is not used or changed.
Alibaba Sandbox snapshot capability was also tested without model calls and
returned `400: sandbox runtime does not support snapshot`; no snapshot support is
assumed. The selected Docker backend therefore provides filesystem snapshots,
reusing the pinned Harbor0.23 native loop, offline tmux, teacher/client/scorer and
exporter. Global environment repairs require full filesystem image snapshots;
/app-only copies are insufficient. Snapshot image IDs/manifests are retained,
including held attempts; do not prune these study images. Docker daemon and
other experiments/images are untouched. Solvers have no host mounts or API
credentials. These selected offline-repair tasks, builds and fresh graders use
network none, matching the old Alibaba solver's outbound isolation. This backend
difference must be reported when comparing setup/wall time
against the previous Alibaba runs; interaction/token counts are more comparable.

Original run_tests scripts do not reliably propagate pytest's exit status.
The external grader therefore requires every specified test ID to be PASSED,
restores frozen original public test files in a separate grading container and
checks a private failing canary. Missing/skipped results and blanket-pass stubs
are rejected. Gold and initial controls use the identical grading contract.

Persistent study root:
`/vePFS-Mindverse/user/intern/fanqi/tb4-research/cli-gym-pilot-20261104`.
Sources are committed then exported into a distinct read-only frozen checkout.
`prepare.py` publishes an atomic incremental plan; the existing production
coordinator dispatches only prepared units and performs controls before models.
Four student slots and two score-prefill slots are scoped to this new study.
The existing unit pipeline may run fewer than four students while waiting for
experts; do not call four task workers four active students.

Compare with the old run's 17 closed experts (mean147 interactions/71.14min),
and the two new admitted students (13 interactions/20.22min; resumed Coq19
cumulative interactions/22.24min suffix elapsed). The latter resumed timing is
not directly comparable to a fresh full episode. Report all six selected cases,
preparation/controls separately, expert and student phases, peak context,
generation/score requests and tokens, complete/held outcomes, and SFT files.
Small-pilot throughput is descriptive; no stable success-rate claim is implied.
