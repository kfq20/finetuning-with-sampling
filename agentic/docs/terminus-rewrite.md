# Terminus-2 rewrite protocol v1

Selected 2026-11-02 on `research/tool-boundary-rewrite`. The maintained new entry
is `append_rewrite.terminus.trial`; `claude_*` and `run.py` are historical runners.
No old result, frozen runtime, native history or outcome is rewritten.

## Runtime and message contract

Harbor 0.23.0, JSON parser, native tmux executor. `runtime.PIN` checks six source/
template identities before constructing an agent. No model call occurs on import.
The controller runs the LLM and holds Fleet credentials; the solver sandbox has
no Fleet administrative key. `environment.SDKEnvironment` is independent of CC.

A block is the entire raw assistant JSON command batch, followed by the actual
native terminal observation. Do not split a multi-command batch into synthetic
independent tools. ATIF's synthesized `bash_command` calls are analysis metadata,
not candidate strings for likelihood scoring. Preserve original assistant bytes.
Public `analysis`/`plan` are native action fields; hidden provider reasoning is
not imported into public histories. Final completion requires Harbor's two-step
confirmation; a dead tmux session is an execution error, not success.

`ReferenceLLM` adds a tagged expert suffix only to actual generation input, while
native `Chat.messages` retains the public user prompt and assistant output.
Provider response-chain IDs are disabled to prevent reference persistence. The
backend journal is private evidence of privileged generation. Scoring receives
ONLY the public native prefix and raw candidate assistant text; SFT previews mask
all prefix and terminal messages. Tokenizer-aligned training masks remain separate.

The study fixes `max_turns=None`, JSON, no hidden reasoning reinjection, full
message capture, and **no summarization** for comparable frozen-prefix research.
Context overflow is an explicit error, not a silent prefix replacement. This is
a study setting, not a claim of identical official benchmark settings. Output and
wall-clock limits are supplied explicitly at launch; no new global budgets.

The adapter overrides Harbor's blanket three-attempt `_query_llm` retry: ambiguous
provider failures stop the current trial; there is no new paid completion,
endpoint fallback or repeated tool execution. Confirmed SSE completion and exact
returned model identity are required by the controller Fleet backend. Jobs
fallback is forbidden on this selected deployment. Incomplete/length/error results
are execution errors, not semantic zeros. Transport cancellation cannot guarantee
that an upstream provider has stopped computing; preserve its journal and cost.

## Environment boundaries and branch interface

`before_model(agent, public_history, pending_prompt)` is awaited at every actual
native model boundary. A controller may hold this callback while capturing state.
`agent.capture_boundary(...)` binds public history, pending prompt, pending
completion status and a trusted actual state ID/scopes. Command observation
windows DO NOT establish that processes are quiescent. Cwd, environment variables,
tmux buffer/input, running jobs and external databases are state as well as files.
A file tarball alone is never admitted as a portable terminal checkpoint.

The new first-class raw-text utilities provide checkpoint hashing, scorer inputs,
strict candidate validation and contiguous message-level SFT previews. They do not
convert Claude Code native sessions into Terminus prefixes. Existing CC expert
behavior can be privileged reference, paired with a newly declared fresh Terminus
task. This changes conditioning and gets a new study identity.

Portable fork/restore for arbitrary live tmux/process state needs a sandbox
snapshot adapter and independent restore controls. The live hook supports holding
the original session; it is not a portable snapshot implementation. Backend
forced input/candidate likelihood also remains unavailable on tested Mint routes.
Therefore this release enables native rollout and boundary integration, **not a
claim that end-to-end MCMC selection and arbitrary checkpoint branching are done**.
The old `tool_blocks` file fixture remains a separate legacy regression suite.

## Entry and verification

```
PYTHONPATH=agentic/src python -m append_rewrite.terminus.trial \
  --inputs /persistent/study/inputs.json --fleet-config /private/fleet.json \
  --sandbox-credentials /private/sandbox.env --output /persistent/new-attempt \
  --timeout 28800 --max-output-tokens 128000 [--reference /private/expert.txt]
```

The input manifest declares `protocol=harbor-terminus-2-json.v1`,
`history_import=fresh_task`, task/state/cwd/artifact_paths, and path/sha256 bindings
for instruction, state_manifest and runtime_binding. State manifest enumerates
all restored files with bytes SHA256 and POSIX mode. Output directories are
exclusive. Original grading/capture/error journals are retained, no retries.
Run controls and bind the frozen task/grader release before any new paid study;
the entry alone is not admission. End-to-end fresh-capture regrading still belongs
to the study's independent acceptance gate.

```
PYTHONPATH=agentic/src python -m unittest discover -s agentic/tests -q
REWRITE_NATIVE_TMUX_TEST=1 REWRITE_TEST_ROOT=/persistent/test-root \
  PYTHONPATH=agentic/src python -m unittest discover -s agentic/tests \
  -p test_terminus_native.py -v
```

The native integration uses real isolated tmux, three scripted model responses,
a real command/file/observation and native completion confirmation. Zero inference
requests. Its tmux socket and log paths are unique, no shared server is changed.
