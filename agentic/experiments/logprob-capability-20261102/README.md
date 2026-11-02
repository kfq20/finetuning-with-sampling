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
