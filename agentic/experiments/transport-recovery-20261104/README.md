# Transport recovery — 2026-11-04

**Stopped by explicit user request on 2026-11-04. Do not resume automatically.**
`PRODUCTION_SELECTION.json.user_stop` and the selected roots' `USER_STOP.json`
are authoritative. The compatibility `STOP_PROVIDER` marker records a user stop,
not a provider policy failure. At 08:08 +08:00 no owned production/scoring process
remained; all four interrupted file captures were retained, and their four
sandbox IDs were absent from the running-sandbox list. The 16 admitted SFT files,
17 normal student results, original failures/cost evidence and 14 unattempted
inputs remain preserved. Interrupted attempts are cancellations, not model zeros.
Evidence: `data/user-stop-20261104/`. Other experiments are outside this stop scope.

Owned MindLab root: `/vePFS-Mindverse/user/intern/fanqi/tb4-research/projection-agent-20261102`.
Evidence: `data/transport-diagnosis-20261104/`. Existing raw attempts remain immutable.

Historical zero-generation scoring had 330 HTTP 499 attempts lasting 30.39–35.48 seconds, before the client's 120-second socket timeout. The same failed Coq candidate later returned HTTP 200 in 16.58 seconds. All eight cached candidates also succeeded concurrently (15.65–35.71 seconds). This excludes a universal 30-second timeout and malformed candidates; it does not prove the server-side cause of historical cancellations. Old clients discarded HTTP error bodies/headers, preventing request-level attribution. Five teacher 502s occurred before SSE, lasting 0.53–21.93 seconds. They are transport errors, not model zeros or 600-second stream truncations.

Repair preserves the algorithm and model routes: four student episodes, eight candidates per block, full reference-free input-token scoring, and no intermediate verifier selection. A shared two-slot scoring-prefill gate limits request fanout independently of student concurrency. Zero-generation scores retain five bounded attempts with jittered backoff; generation/expert POSTs are never automatically replayed. Capture safe response headers (including Fleet record IDs), bounded private HTTP error bodies and timing for future attribution. This is client-side mitigation; no serving deployment restart or timeout change is claimed.

`python -m append_rewrite.terminus.blockwise` repairs only an explicitly selected failed block. It checks the exact public prefix, referenced generation token IDs, normal generation finish, and returned score token IDs. Existing valid scores are reused; missing scores are recomputed without action generation. Tools never execute in this command.

An explicit `coq-files-v1` continuation adapter may reconstruct a reviewed native command prefix, including its lost temporary compiler files/cwd, then compare the resulting `/app/project` and `/app/output` hashes/modes with the retained original capture. It resumes only at the bound pending block, reusing all eight original candidates. It is not arbitrary process/tmux snapshot restoration. Any state mismatch blocks model continuation. Other domains require their own state audit and remain held if state cannot be restored reliably.

New unclaimed inputs may move to a frozen four-lane run, reserving their old paths so the old coordinator skips them. Active old workers continue unchanged and reserve student capacity until exit, preventing overlap beyond four. Previously paid failed attempts are not redispatched; the explicit Coq continuation is linked to its original failed attempt and is not a new cold replay. Never count repaired scores alone as completed trajectories or SFT data.

## Selected run and observed recovery

Selected frozen source: `source-transport-recovery-20261104-v2`, commit `c8dbe882bee790fc8721d774f7de179f50b8eaa8`; run `data/append-production-transport-v1`. Authority remains `PRODUCTION_SELECTION.json`, with admission and PID/start-tick receipts in `data/transport-recovery-20261104/`. The plan contains 41 never-dispatched inputs and one continuation of the original Coq4 attempt. Three already-paid legacy workers were preserved and reserve capacity until exit. Queue admission is not proof that four students are actively inferring.

The actual MindLab SDK suite ran 106 checks: 104 passed, two skipped. Process-level slot checks verified two scoring prefills and four total student slots including a retained legacy reservation. Coq file reconstruction matched all retained file hashes/modes and stopped before inference during its dry-run. The first dry-run's parsed/native command-type mismatch was corrected before any paid continuation; its evidence and source v1 remain preserved.

At 2026-11-04 00:48:39 +08:00, both failed Coq4 block9 and Console block15 had complete eight-candidate decisions with zero new candidate generation and zero tools executed by the score-repair commands. Coq4 then resumed from block9, completed decisions9–11 and reached block12; 16 new scoring calls had succeeded without a new HTTP error at that observation. Console remains an offline score recovery, not a resumed or completed trajectory. Original failures, candidates and captures were not overwritten. All later counts require live verification.

`data/transport-diagnosis-20261104/provider-correlation.json` retains the historical failure times, body digests and endpoint for provider correlation; historical failed-response request IDs cannot be reconstructed from discarded headers. Their 499 window was 2026-11-03 13:33–22:40 +08:00. No explicit controller HTTP proxy was configured. The Fleet deployment was still serving its original run/model. Current replay success is mitigation evidence, not proof that the provider-side cancellation cause is fixed.
