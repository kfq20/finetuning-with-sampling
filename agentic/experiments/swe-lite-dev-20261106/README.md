# Lightweight repository-repair evaluation pilot

SWE-bench Lite official **dev**, six tasks: first two lexicographic instance IDs
in each of marshmallow-code/marshmallow, pydicom/pydicom, pylint-dev/astroid.
No task selection by gold patch length, model response or outcome. The complete
dev split has23 tasks; the official test split has300. This pilot is neither
an official300-task score nor evidence of broad SWE generalization.

Base and epoch1 step34 method/expert Qwen3.8-27B Fleet models each run Pass@1.
Same Terminus-2, nonthinking/.6, context262144/output128000,1800s agent deadline,
no max_turns, one generation per turn, no paid retry. One concurrent task perarm,
three total; existing TB2.1/epoch2 training untouched. Unequal backend placement
and concurrent serving load must be recorded as timing confounders.

Before model dispatch, pin dataset/source/parser/image digests and run actual
Harbor/Ali NOP0 and gold1 controls for all six. Admit each passing task
independently; preserve failed controls as environment holds, without replacing
tasks or counting them as model0. Official eval_script and required
FAIL_TO_PASS/PASS_TO_PASS tests determine binary success. Official parser bodies
are unchanged; standalone imports replace only package type hints/status enum.
Missing expected tests or execution errors are unknown, never valid model0.
Gold and grader are uploaded only for oracle or post-rollout grading. Solver
gets original issue, repository and ordinary project tests, without hints_text,
gold patch, FAIL_TO_PASS lists or evaluation script.

`run.py pipeline ROOT` is finite and exclusively locked; root is never reused for
paid retries. Source is frozen in ROOT/runtime/source, raw task records in
ROOT/source. Root selected on ECS:
`/mnt/ecs-tb4/evaluations/qwen38-swe-lite-dev6-20261106-a1`.
Plan/admission/model identities/dispatch claim are separate receipts. No Git
secrets, large raw traces or execution data. `collect` reports counts only;
per-task trajectory metrics and paired speed analysis follow completed trials.

Sources: https://www.swebench.com/lite.html
https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite
https://github.com/SWE-bench/SWE-bench

## Initial environment finding

Pydicom-1139 official gold fixes all three F2P tests, but two required P2P tests
fail because pytest8 does not invoke the legacy nose-style `setup` hook (missing
`self.tag`). This is an environment control hold, not a model failure. Original
image, gold, test logs and score are preserved. No requirement is removed.

Harbor truncates long trial directory names; admissions and analysis use the
canonical `result.task_name`. Source-frozen finite followup reuses original
control receipts, waits for the original zero-model preparer to finish and holds
an exclusive lock before model dispatch. No model or control replay for naming.
Selected orchestration source f91e522, original shared inference library ecb151b;
`active_runtime_selection.json` binds both. Original preparer/failed admission
and retired idle handoff receipts remain under the same run root.

## Zero-inference runtime correction

Stock images lack tmux. Initial model jobs failed setup **before any model POST**;
all were held/retired by exact owned PID/start identity and original receipts
preserved. Selected repair root is
`/mnt/ecs-tb4/evaluations/qwen38-swe-lite-dev6-20261106-a2`, bound explicitly by
a1/startup-repair-selection.json and a2/active_runtime_selection.json.

`prepare_offline.py` bundles public existing Ubuntu tmux, its loader/libraries and
terminfo into a SHA-pinned isolated overlay. Only tmux uses its bundled loader;
project Python, dependencies, source and base image remain unchanged. It does not
install anything on the shared host or change a cached base template. A named
controller-only adapter uploads the same public overlay to every model arm.

Five actual Qwen/Terminus Harbor install-only trials must finish without error
and zero inference, then actual NOP0/gold1 controls check the overlay. Exact prior
controls remain explicitly bound for the other tasks. Only then dispatch five
admitted tasks perarm,15 model attempts; original6-task denominator retains the
one environment hold. No paid model attempt is replayed. Finite analysis exports
trajectory counts, tokens, context and timings after completion.
