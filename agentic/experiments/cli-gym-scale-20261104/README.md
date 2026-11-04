# CLI-Gym acquisition: rolling dispatch

The selected ECS run is `/mnt/ecs-tb4/cli-gym-scale-20261104/rolling-acquisition-20261104`.
Read root `campaign-selection.json`, `campaign-progress.json` and
`transport-selection.json` before using any historical launch receipt.

- `rolling.py` owns the campaign lock, validates the existing catalog, publishes
  the cumulative hash-bound SFT pack, prepares source groups, and appends ready
  immutable inputs to one discovery plan. It does not call a model.
- `production.batch` provides the single explicitly sized queue (currently16 slots). Adopted workers retain
  their exact PID/start identity and original output directory. New output lives
  in the rolling run. A completed/failed original attempt is never redispatched.
- Source preparation remains in groups of100, using the existing Docker
  preparation script and per-task controls. When fewer than the configured worker capacity of prepared inputs
  remain unclaimed, the producer starts the next source group. This watermark
  does not increase model concurrency or impose a token budget.
- Student capacity16, score-prefill capacity4, candidates8, task deadlines,
  native Terminus protocol, verifier/fresh-score and training admission are
  unchanged. Existing model attempts finish normally or retain original errors.
- `activate_rolling.py` is an already-executed, exclusive one-time scheduler
  handoff. Do not rerun it as a resume command. Check `ACTIVATED.json`, current
  process identities, `source-binding.json` and `ACCEPTANCE.json` first.

The existing500-valid-SFT objective, source exhaustion, user/provider stop, and
physical storage admission remain the stopping conditions. Already-published
work drains when the production target is reached. Errors are not model0 or SFT.
Raw traces, credentials, images and results stay outside Git. Selected code is
frozen; a later documentation commit does not change that running identity.

Current handoff receipt is selected by `active_runtime_selection.json` →
`current_activation_receipt`; the initial8-slot `ACTIVATED.json` is historical.
Completed failure processes with saved error/context/history may be retired by
the producer after bound evidence, releasing a slot without replaying the task.
Healthy episodes and normal completed scores are never retired this way.
