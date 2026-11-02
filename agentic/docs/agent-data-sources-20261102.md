# Data for agentic projection/rewrite — source audit, 2026-11-02

## Original paper

[Finetuning with Sampling, §5.1](https://arxiv.org/html/2610.02140v1#S5.SS1)
uses three independent text-domain datasets, not terminal environments:

| Domain | Source | Training | Evaluation | Expert material |
|---|---|---:|---:|---|
| Chemistry | SciKnowEval Chemistry L3 | 1,800 | 600 | GPT-5-generated solutions |
| Math | MATH levels 3/4/5 | 8,230 | 1,024 | Existing expert solutions |
| Medicine | HuatuoGPT-o1 SFT | 19,704 | 1,000 from separate RL set | Provided expert responses |

These are separate experiments, not evidence that agentic rewrite requires a
fixed total of 29,734 examples. The study supplies no terminal snapshots, tool
observation replay system or agentic sample-complexity result. Its expert traces
include reasoning, but our public action/observation protocol excludes hidden
provider reasoning. Terminal success therefore needs its own empirical scaling
study and contamination-safe evaluation.

## Public agent resources

Counts below describe publisher claims and currently displayed row counts, not
our admitted success count. Direct metadata API requests failed from this workstation; the attempted queries
and error types are retained in
`../experiments/terminus-migration-20261102/data-source-identities.json`.
Numbers and licenses below come from the linked publisher cards. Revision pinning
and row-level admission are required at ingestion, and have not been completed.

| Source | Scale / assets | Fit for this work | Card license |
|---|---|---|---|
| [Nemotron-Terminal-Corpus](https://huggingface.co/datasets/nvidia/Nemotron-Terminal-Corpus) | 366,154 displayed rows; ~226k dataset-adaptation and ~140k skill-synthetic trajectories | Large teacher-trace pool; inspect subsets, success provenance and parser compatibility | CC-BY-4.0 |
| [Nemotron-Terminal-Synthetic-Tasks](https://huggingface.co/datasets/nvidia/Nemotron-Terminal-Synthetic-Tasks) | Public task archives, instruction/environment/tests, nine shared domain images | Strong starting point for executable rewrite tasks; archive task count still requires enumeration | CC-BY-4.0 |
| [OpenThoughts-Agent-SFT-100K](https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-SFT-100K) | Card says 100k; HF displays 94,334 rows; GLM-4.7-AWQ / Terminus-2 / Daytona | Closest harness match; sources SWE-smith, SuperUser, Tezos, IssueTasks; >=5 model turns filter | Apache-2.0 |
| [OpenThoughts-Agent-v1-RL](https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-v1-RL) | 728 metadata rows with packed tasks, Dockerfile and verifier | Small executable bring-up pool; nl2bash can be too easy and is not long-horizon evidence | Card does not declare a license in inspected metadata |
| [SWE-smith](https://huggingface.co/datasets/SWE-bench/SWE-smith) | HF displays ~59.1k task rows; original release 50k+, 128 repo environments | Versioned repository states, test-based scoring and Docker images; mostly SWE, not all TB domains | MIT |
| [SWE-smith trajectories](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories) | Public trajectories, `resolved`, patches, instance IDs; official documentation identifies a 5k expert training set | Join by instance ID, select confirmed resolved traces; SWE-agent history becomes reference, not a native Terminus prefix | MIT |

[Official SWE-smith assets documentation](https://swesmith.com/getting_started/assets/)
links environments, task records and expert trajectories. Dataset rows, unique
tasks and successful trajectories must be counted separately. Multiple released
formats/splits can encode the same underlying run; do not add them blindly.
NVIDIA's ~140k synthetic figure counts trajectory samples, not verified distinct
environments. OpenThoughts' 100k-versus-94,334 discrepancy is retained explicitly.
These corpora may share sources, including SWE-smith: sizes are NOT additive.
Card license does not establish every underlying repository/data/artifact's terms;
retain the source/component/license chain before training admission.

## What about Terminal-Bench 2.1 / 3 / 4?

The [official benchmark index](https://www.tbench.ai/benchmarks) links all versions,
including task repositories and Harbor Hub. They are public evaluation assets.
The [TB2.1 repository](https://github.com/harbor-framework/terminal-bench-2-1)
also documents public job uploads and trajectory review. Public leaderboard
trajectories can support failure analysis, harness validation and difficulty
comparison. They are not automatically a decontaminated expert-training dataset.
The benchmark site explicitly marks benchmark data to stay out of training
corpora. Keep all official benchmark tasks, solutions, traces and close duplicates
in evaluation-only storage; do not treat an older version as a clean training split
for TB4. Community trace scrapers inherit this contamination issue.

Use TB as held-out evaluation and domain reference, and training-oriented corpora
as the volume source. New in-domain tasks should use independently sourced projects,
data and contracts rather than copying benchmark solutions or near-duplicate tasks.

## A scalable acquisition route

1. Metadata-first ingest: pin revisions, enumerate task/run IDs, source license,
   harness, teacher, reported outcome and source-family. Deduplicate shared tasks,
   traces and source repos across NVIDIA/OpenThoughts/SWE-smith/our append data.
2. For offline SFT or textual rewrite, use vetted public expert transcripts.
   This requires no reconstruction of every historical environment checkpoint.
3. For environment-grounded rewrite, admit the intersection of a versioned task,
   recoverable initial image/state, executable verifier and successful expert
   actions. Start at task initialization. Rebuild intermediate states only by
   audited action execution in an isolated sandbox, checking observations and
   artifacts at each boundary. Arbitrary tool calls may be nondeterministic;
   transcript availability alone never certifies a restorable checkpoint.
4. Fresh student Terminus rollouts use actual command feedback. Old CC/SWE-agent
   expert transcripts remain privileged reference, not fabricated native history.
   Retain failed/error runs. Candidate selection waits for genuine input-token
   scoring; reference-conditioned output LP is the wrong distribution.
5. Measure learnability on independent tasks/repositories: compare unreferenced
   student, referenced student and expert controls; record success improvement,
   copy dependence, action likelihood and cost. Don't spend a full unreferenced
   rollout on every easy example before a pilot establishes the filtering value.
6. Retain append evolution for hard boundary cases, stateful dependencies and
   domain gaps. It produces valuable depth and controlled contrasts, while public
   task pools provide breadth and volume. Multiple candidates from one task are
   correlated augmentations, not additional independent environments.

Suggested first scaling study (proposal, not launched): choose 100–300 executable
unique tasks across several source families; establish native compatibility and
reward validity, then compare ordinary expert SFT versus reference rewrite at
matched task count and training-token count. Scale admitted pools to 1k/3k/10k
only after measuring benefit. Hold out source repositories/families and official
TB entirely. The scientific bottleneck is useful diversity and grounded
verification, not the number of transcript windows alone.
