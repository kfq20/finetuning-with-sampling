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
Harbor/Ali NOP0 and gold1 controls for all six. Official eval_script and required
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
