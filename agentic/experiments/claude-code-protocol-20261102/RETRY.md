# Buffered request retry — opt-in transport

The paired Coq attempts exposed Anthropic SSE errors after HTTP200 and partial
generation. Native Claude Code ended with is_error=true. A later provider error
frame identified `upstream stream interrupted: error decoding response body`.
The failing requests lasted35–45seconds. They were not successful task endings.

The original passthrough relay did not retry upstream requests. Retrying after
forwarding partial content risks duplicated tools. The new opt-in relay instead:

1. Sends early SSE headers and comment heartbeats to keep the downstream alive.
2. Buffers the complete model response in trusted gateway memory. It validates
   message_start/model, indexed block lifecycle, unique tool IDs, assembled tool
   JSON, stop_reason and message_stop before forwarding any model content.
3. On retryable transport/SSE errors or408/502/503/504, discards the unforwarded
   response, logs the failed attempt with unknown usage and applies2/4s backoff.
   A retry sends the identical request to the identical endpoint/model. It does
   not replay historical tools or restart the task.
4. For401/403, model mismatch, other permanent errors or exhausted attempts,
   fails explicitly; auth errors also STOP. No fallback and no implicit429/quota
   retry. No retry occurs after delivery to Claude Code begins.

Enable explicitly with `claude_trial --buffered-upstream-attempts 3` (total
upstream attempts, not three extra attempts). Default remains passthrough and no
retry. Both paired arms must use the same transport policy. No running frozen
runtime was modified and no new model requests have tested this policy yet.
Response buffering delays model content visibility until completion; comment
heartbeats remain live. Buffering is a reliability tradeoff, not a provider fix.
Every failed generation may be billable; preserve each attempt and unknown usage.

Six no-model fault-injection tests cover late SSE failure after a tool block,
valid fragmented tool JSON, malformed tool JSON, auth failure, model mismatch and
bounded503 retry. The late-error test verifies only the successful response is
delivered, so the failed tool block cannot reach the CLI. Whole suite27pass.

The first paired runtime captured the task output directory on an error but did
not capture the project workspace or Coq /tmp scratch. Those old sandboxes are
retired; no lossless same-state resume is claimed. Future error closure also
captures /app/project and /tmp Coq .v sources. Compiled caches can be rebuilt;
this is file recovery, not a process/memory snapshot. Original failed attempts,
submission hashes and snapshot scores remain unchanged.
