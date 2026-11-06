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

## Completed verification

2026-11-07 00:01CST:123,677 closed journals archived,0errors,45.18GiB allocated
space recovered; available5.18→50.03GiB under concurrent writes.415training-file
SHAs and all terminal contexts unchanged;12independent restoration samples pass.
All original image IDs preserved, selected SWE controller PID/start unchanged.
The finite worker completed; no daemon/model restart or paid replay occurred.
The source root's ARCHIVED_API_JOURNALS_20261106.json points to the authoritative
ledger. Full audit and large raw records remain outside Git.

## Wave2,2026-11-07

`archive_evaluations.py` handles only five explicit historical eval roots.
Per-trial finished marker and file mtime must both be at least10min old, no open
FD/symlink/multiple hardlinks. Failed/timeout partial streams can be archived
without requiring a successful model decision; their original failures remain.
The current SWE300 root is explicitly excluded. All historical result/trajectory
SHAs are protected before/after; ledgers bind each journal to its result SHA.

Selected source65b133a;3actualSDK tests pass. Finite worker completed25,349files,
0errors,88.57GiB attributed recovery; free49.02→132.44GiB with concurrent writes.
1,237result/trajectory hashes and415training-file hashes unchanged;12independent
restoration samples pass, original images and SWE controller identity preserved.
Audit: `/mnt/ecs-tb4/audits/storage-recovery-20261107-wave2`.
Each source root has its own authoritative-archive notice. No model/Docker
restart, paid replay, image deletion, task simplification or new automation.
