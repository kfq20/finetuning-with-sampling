# Selected Qwen logprob capability probe

Real minimal probes against the existing Qwen/Qwen3.8-27B deployment, without
agent tools, task rollout, retry, fallback, deployment changes or training.
Inference credentials and full responses remain in external private storage.

Observed:

- Chat `logprobs=true,top_logprobs=1`: HTTP200,2 generated positions with finite
  probabilities. Generated-token probabilities are available.
- Completions `echo=true,logprobs=1`, supplied answers4 and9 under the same raw
  prefix: HTTP200,15 prompt tokens, but only1 logprob entry for the newly generated
  token. Echo text is not proof of input probabilities. The placeholder offset-1
  is not an input-token position.
- `prompt_logprobs=1` and native `return_logprob=true,logprob_start_len=0` extensions
  also return only the single output logprob; no input probabilities are exposed.
- Own deployment `/v1/models` matches the selected alias. Tested OpenAPI/native
  model-info discovery routes return404. This does not prove every possible
  private backend scoring route is unavailable.

Five tiny inference requests total,6 actual generated tokens across them; no
whole task sampling. The scorer required for projection sampling is NOT admitted
on these results. Do not substitute reference-conditioned generation logprobs for
unreferenced teacher-forced candidate likelihood.

Entry: `python -m append_rewrite.logprob_probe --fleet-config PRIVATE_CONFIG
--protocol FROZEN_PROTOCOL_JSON --output FRESH_EXTERNAL_DIR`. The default runs
one generated-output test plus two forced-input echo tests. `--extensions-only`
runs two extension checks without repeating earlier generation tests. Each
inference request is max4 or1 new tokens and no automatic retry is performed.

Next integration needs a verified endpoint that accepts exact unreferenced input
IDs plus candidate IDs and returns their original, untruncated token logprobs,
aligned to tokenizer/template/weights identity and target positions. Both likely
and unlikely forced tokens must be scored. Grammar-constrained output probabilities
or top-k candidates that omit the requested token are not equivalent evidence.
Native Claude Code history/tool schema tokenization still needs separate binding.

## Subsequent native-route result (user-provided, 2026-11-02)

The original tests above describe only the tested OpenAI-compatible and extension
routes. The user subsequently obtained HTTP200 from the deployment's native
`/generate` route with max_new_tokens=0, return_logprob=true,
logprob_start_len=0 and return_text_in_logprobs=true. Metadata reported 15 prompt
tokens, zero completion tokens, and input_token_logprobs entries containing
[logprob, token_id, token_text]. Candidate `4` had LP -0.002393835224211216.
Request ID ddc230ee77594e54bc21557b02ffde91. This is user-supplied evidence, not a
new probe executed by this patch. Original responses remain unchanged.

Capability discovery is resolved. `append_rewrite.terminus.scoring` implements
the native scorer, preserving exact input IDs, ignoring only the initial null LP,
and aggregating only candidate positions. It rejects incomplete coverage,
generation, null candidate LPs and token-ID drift. End-to-end admission still
requires generation/scoring tokenizer and chat-template parity. Five new
model-free scoring regressions pass; no new model/API requests were made.
