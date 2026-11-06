# Data-volume recovery,2026-11-06 night

User requested reclaiming the nearly full ECS data disk. No inference, model
replay, image/volume pruning, shared daemon lifecycle or active trial change.
Selected finite source targets only the completed CLI-Gym rolling acquisition's
teacher/student API wire/request/response files. Require producer completion,
no process reference, no open FD, non-symlink and unique hardlink, stable inode,
size/mtime and preserved terminal context. Keep trajectory/decision/grades/SFT.

Reuse the tested gzip archive primitive. Verify full decompression bytes/SHA,
fsync provenance before removing redundant plaintext. Archives and ledger are
AUTHORITATIVE original bytes, not disposable backup. Decompress for future raw
request/logprob audits. Retain context and source proof, result hashes and costs.
Two finite IO workers; live primary SWE300 controller continues unchanged.

Audit root: `/mnt/ecs-tb4/audits/storage-recovery-20261106-night`.
`plan.json`, `ledger.jsonl`, `progress.json`, pre/post identity and disk snapshots
are external artifacts. Attribute recovery by targeted file allocated blocks,
not the full disk delta, because independent experiments write concurrently.
