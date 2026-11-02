# Shared native Claude Code protocol

Prospective protocol unification, with zero new model requests. Historical
custom-controller trials and the original DeepSeek traces remain unchanged.

Both model profiles now use pinned Claude Code2.1.207 and the same Harbor0.23
ClaudeCode base via frozen tb4-foundry OfflineClaudeCode. The thin UnifiedClaudeCode
wrapper appends an optional expert reference to the current user instruction.
History is an observable-only native JSONL import loaded through Harbor.load and
CLI --resume; it is no longer serialized into the new user prompt. Imports have
new IDs and explicit source provenance, not a claim of original opaque replay.

Four real pinned-CLI cases against a deterministic loopback Anthropic fixture
passed: DeepSeek/Qwen model IDs x reference/no-reference. Each restored the same
115 public messages and49 tool pairs, executed a genuine Bash call, returned its
real feedback, then completed normally. Tool-schema hashes match; system hashes
match after model-identity normalization. Private thinking was absent. Provider
inference calls were0; synthetic fixture usage/cost is not experimental usage.

The tests also caught and preserved an unresumed run: constructing with a seed
and calling run is not sufficient; the Harbor load entry must be used. Admission
checks the actual CLI session ID and actual on-wire historical tool inputs,
outputs, error flags and public text, not merely process startup.

Native CLI asks for adaptive thinking/effort max and128000 output tokens. These
settings are shared requested hints, not evidence of provider support/capacity.
Real Qwen Anthropic-provider compatibility and a new paired rollout remain to be
tested separately. Old custom-harness results do not serve as native-CLI controls.

Compaction/summary records, sidechains or missing source project keys fail closed
until a reviewed adapter exists. Original hidden reasoning is never transferred.
The validated sample is Coq append3; this is not blanket admission of the corpus.
Source and external admission/run identities are recorded in the study ledger.
