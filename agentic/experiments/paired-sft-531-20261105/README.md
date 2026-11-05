# CLI-Gym paired531 SFT → Fleet → TB2.1

User authorized both formal SFT arms and post-training evaluation on2026-11-05.
Use the validated direct MinT SDK route; this is not a MindForge training job.
The prior one-step checkpoint is retained and is not either arm's initializer.

## Fixed configuration

| Parameter | Both training arms |
|---|---|
| Base / initialization | Qwen/Qwen3.8-27B; independent fresh adapters, LoRA initialization seed42 |
| Dataset | Same531 ordered task identities; method vs corresponding expert successful trajectories |
| Training objective | Full-episode next-token cross entropy; binary assistant-only weights, correct one-position target shift |
| Context / template | Exact release token IDs and masks; frozen text template/tokenizer6212f739…; no renderer rewrite |
| Supervision | All admitted assistant messages including public JSON analysis/plan; no extra hidden reasoning_content |
| Epoch / batch / updates | 1 / 1 / 531; accumulation1; no held-out rows |
| Shuffle | Python random.Random(42), identical task order |
| Maximum length | 131072; retain entire episodes, no truncation or extra packing across episodes |
| LoRA | rank32; attention+MLP enabled; unembedding disabled |
| Adam | LR1e-4, beta1=.9, beta2=.999, eps1e-8, weight decay0, grad clip1 |
| Schedule | Constant; warmup0 |
| Loss scaling | SDK cross_entropy default, binary masks, no additional client normalization |
| Checkpoints | State each100 updates and final531; final sampler weights also saved |
| Model selection | Final531 fixed in advance; no choice based on TB scores |
| Training parallelism | Two independent clients/sessions; no resume from one-step |
| Failure policy | Write-ahead update intents; no blind replay of ambiguous/paid calls; retain failed arm and allow other arm to finish |

Backend GPU allocation, LoRA alpha/dropout and training dtype are not client-set
by this SDK. Record get_info/backend responses, do not invent these values.
This is a matched-task/epoch/parameter comparison: method1,526,318 versus
expert2,225,915 supervised tokens. It is not an equal-token-budget comparison.

## Serving and evaluation

All three arms use Fleet `h20-qwen38-tp4`, Qwen3.8-27B FP8, priority0.
Base uses source=base; trained models use source=lora and their final state paths.
No shared MinT sampler is created or repaired. Independent deployment names:
`fq-qwen38-{base,method,expert}531-sft-20261105-a1`.

- Official TB2.1:89tasks, dataset commit7131e4375048a0e408a8fb404b5f499d726b695b.
- Reuse hash-verified Harbor0.23/Terminus-2 runtime-v2, original instructions/tests,
  pinned mirrored image digests and recorded Alibaba resource rounding.
- Alibaba Sandbox; unreferenced Pass@1, one proposal, four concurrent trials perarm
  (maximum12 across three arms); no automatic paid retry.
- Pinned tokenizer/direct input_ids, native JSON protocol, temperature.6,
  context262144, max output128000, max_turns=null, standard summarization enabled,
  interleaved_thinking=false. Task timeouts unchanged, multiplier1.0.
- Fleet16-token loading probe; then fix-git canary perarm. Valid zero is allowed;
  canary execution/capture failure holds that arm. Reuse each canary once in89.
- Primary score: full required-check success is1; valid failure0; infrastructure,
  missing rewards/captures and unknown outcomes separate. No missing trial imputation.
- Base is evaluated anew on Fleet; previous direct-HTTP results remain historical.
  Training overlap/generalization claims require a separate dataset audit.

## Durable identities

Local data/plan/status:
`/Users/fancy/project/finetuning-with-sampling-data/paired-sft-531-20261105-a1`.
ECS evaluation:
`/mnt/ecs-tb4/evaluations/qwen38-paired531-sft-20261105-a1/{base,method,expert}`.

`plan.json` freezes the complete public configuration, original dataset hashes,
source commit and runtime hashes before dispatch. Eacharm owns claim/step intents,
acknowledgements, checkpoints, deployment and evaluation handoff receipts.
Credentials enter the local process via stdin; evaluation credentials travel only
through SSH stdin into an own mode0600 private file, never public configs or Git.
Raw data/results remain outside Git. Run only committed immutable copies.
