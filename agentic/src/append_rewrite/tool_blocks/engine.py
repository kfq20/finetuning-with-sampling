"""One-step branch evaluation with real observations and separate model scoring.

No model inference, retries, scheduler, budgets or automatic training admission.
Adapters are trusted controllers. Receipts bind identity; they are not remote
attestation of an arbitrary untrusted adapter.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict, replace
import math
import json
from typing import Protocol
import uuid
from .trace import Trace, BoundaryError, assistant_action, digest
from .state import StateRef, Execution


class Session(Protocol):
    branch_id: str

    def snapshot(self) -> StateRef: ...
    def execute(self, calls: list[dict]) -> Execution: ...
    def close(self) -> None: ...


class Runtime(Protocol):
    def fork(self, state: StateRef, branch_id: str) -> Session: ...


@dataclass(frozen=True)
class Checkpoint:
    trace: Trace
    state: StateRef
    required_scopes: tuple[str, ...]
    parent_checkpoint_id: str | None = None
    branch_id: str | None = None

    def validate(self) -> None:
        # This is the FULL history at capture time. Do not pair an old cursor
        # with the final environment state from an already completed rollout.
        self.trace.interactions()
        self.trace.require_unprivileged()
        if not set(self.required_scopes).issubset(self.state.scopes):
            raise BoundaryError("Snapshot does not cover required environment state")

    @property
    def checkpoint_id(self) -> str:
        return digest(
            {
                "trace": self.trace.sha256,
                "state": asdict(self.state),
                "required_scopes": self.required_scopes,
                "parent": self.parent_checkpoint_id,
                "branch": self.branch_id,
            }
        )

    def record(self) -> dict:
        self.validate()
        return {
            "schema": "interaction-checkpoint.v1",
            **asdict(self),
            "checkpoint_id": self.checkpoint_id,
        }

    @classmethod
    def from_record(cls, value: dict) -> Checkpoint:
        if value.get("schema") != "interaction-checkpoint.v1":
            raise BoundaryError("Unsupported checkpoint schema")
        state = dict(value["state"])
        state["scopes"] = tuple(state["scopes"])
        checkpoint = cls(
            Trace.create(json.loads(value["trace"]["payload"])),
            StateRef(**state),
            tuple(value["required_scopes"]),
            value.get("parent_checkpoint_id"),
            value.get("branch_id"),
        )
        checkpoint.validate()
        if checkpoint.checkpoint_id != value["checkpoint_id"]:
            raise BoundaryError("Checkpoint history/state/lineage identity changed")
        return checkpoint

    @classmethod
    def capture(
        cls, trace: Trace, session: Session, required_scopes: tuple[str, ...]
    ) -> Checkpoint:
        """Trusted runner calls this while paused at the END of this history."""
        checkpoint = cls(trace, session.snapshot(), required_scopes)
        checkpoint.validate()
        return checkpoint


@dataclass(frozen=True)
class Score:
    model_id: str
    backend_id: str
    history_sha256: str
    action_sha256: str
    sum_logprob: float
    token_count: int
    fixture_only: bool = False

    @property
    def mean_logprob(self) -> float:
        if (
            type(self.token_count) is not int
            or self.token_count <= 0
            or not math.isfinite(self.sum_logprob)
            or self.sum_logprob > 0
        ):
            raise BoundaryError("Invalid assistant-action log probabilities")
        return self.sum_logprob / self.token_count


class Scorer(Protocol):
    def score(self, history: list[dict], action: list[dict]) -> Score:
        """Score assistant tokens under student history ONLY, never reference/results."""
        ...


class Generator(Protocol):
    def propose(self, history: list[dict], reference: str | None) -> list[dict]:
        """Return a complete assistant decision, never observations or partial JSON."""
        ...


@dataclass(frozen=True)
class Verdict:
    passed: bool
    verifier_id: str
    reason: str
    # Passing a LOCAL branch contract is not final task completion.
    scope: str = "local_contract"


class Verifier(Protocol):
    def check(self, session: Session, trace: Trace) -> Verdict: ...


@dataclass(frozen=True)
class Candidate:
    branch_id: str
    parent_checkpoint_id: str
    status: str
    child: Checkpoint | None = None
    score: Score | None = None
    verdict: Verdict | None = None
    execution: Execution | None = None
    reference_sha256: str | None = None
    error_type: str | None = None
    error_code: str | None = None

    @property
    def eligible(self) -> bool:
        return (
            self.status == "evaluated"
            and self.child is not None
            and self.score is not None
            and self.verdict is not None
            and self.verdict.passed
        )

    def record(self) -> dict:
        value = asdict(self)
        value["eligible_for_local_selection"] = self.eligible
        value["training_admitted"] = False
        if self.child:
            value["child_checkpoint_id"] = self.child.checkpoint_id
            value["child"] = self.child.record()
        if self.score:
            value["mean_action_logprob"] = self.score.mean_logprob
        return value


def evaluate_action(
    parent: Checkpoint,
    action: list[dict],
    runtime: Runtime,
    scorer: Scorer,
    verifier: Verifier,
    *,
    reference_sha256: str | None = None,
) -> Candidate:
    """Fork a fresh state, execute once, collect own feedback, then judge/score.

    Schema/receipt/environment errors are holds. A verifier rejection stays a
    semantic rejection. No caller-supplied tool feedback can enter the trace.
    """
    branch_id = uuid.uuid4().hex
    session = None
    try:
        parent.validate()
        if not parent.trace.messages or parent.trace.messages[-1]["role"] != "user":
            raise BoundaryError("No user request/tool feedback awaiting a decision")
        proposal, calls = assistant_action(action)
        messages = proposal.copy()
        call_hash = digest(calls)
        action_hash = digest(proposal)
        # IDs may not collide with any ancestor's calls.
        seen = {i for b in parent.trace.interactions() for i in b.call_ids}
        if seen.intersection(c["id"] for c in calls):
            raise BoundaryError("Candidate reuses a historical tool ID")
        session = runtime.fork(parent.state, branch_id)
        if session.branch_id != branch_id or not session.snapshot().same_content(
            parent.state
        ):
            raise BoundaryError("Fork did not restore the exact pinned state")
        execution = session.execute(calls) if calls else None
        if execution:
            if (
                execution.branch_id != branch_id
                or execution.before_sha256 != parent.state.sha256
                or execution.action_sha256 != call_hash
            ):
                raise BoundaryError("Foreign/stale tool-execution receipt")
            if not session.snapshot().same_content(execution.after):
                raise BoundaryError(
                    "Execution receipt does not match actual final state"
                )
            # Pair validation below rejects wrong/missing/duplicate feedback IDs.
            messages.append({"role": "user", "content": execution.results})
        trace = Trace.create(parent.trace.messages + messages)
        # Verifier is a trusted external control. Its private report is not fed
        # back into student history or included as a training target.
        state = session.snapshot()
        if state.environment_id != parent.state.environment_id:
            raise BoundaryError(
                "Execution changed the pinned runtime environment identity"
            )
        verdict = verifier.check(session, trace)
        if type(verdict.passed) is not bool or not verdict.verifier_id:
            raise BoundaryError("Malformed verifier outcome")
        if not session.snapshot().same_content(state):
            raise BoundaryError(
                "Verifier mutated the branch; score from a separate copy"
            )
        score = scorer.score(parent.trace.messages, proposal)
        if (
            score.history_sha256 != parent.trace.sha256
            or score.action_sha256 != action_hash
        ):
            raise BoundaryError("Score was conditioned on a different history/action")
        score.mean_logprob
        child = Checkpoint(
            trace, state, parent.required_scopes, parent.checkpoint_id, branch_id
        )
        child.validate()
        outcome = Candidate(
            branch_id,
            parent.checkpoint_id,
            "evaluated",
            child,
            score,
            verdict,
            execution,
            reference_sha256,
        )
    except Exception as exc:
        # Preserve branch ID and owned files for diagnosis; never resample here.
        outcome = Candidate(
            branch_id,
            parent.checkpoint_id,
            "execution_hold",
            reference_sha256=reference_sha256,
            error_type=type(exc).__name__,
            error_code=str(exc) if isinstance(exc, BoundaryError) else None,
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as exc:
                outcome = replace(
                    outcome,
                    status="execution_hold",
                    error_type="CleanupError:" + type(exc).__name__,
                )
    return outcome


def generate_candidate(
    parent: Checkpoint,
    generator: Generator,
    runtime: Runtime,
    scorer: Scorer,
    verifier: Verifier,
    reference: str | None = None,
) -> Candidate:
    """Reference goes only to the generator, not scoring/history/SFT export."""
    try:
        parent.validate()
        action = generator.propose(parent.trace.messages, reference)
    except Exception as exc:
        return Candidate(
            uuid.uuid4().hex,
            parent.checkpoint_id,
            "generation_hold",
            error_type=type(exc).__name__,
        )
    return evaluate_action(
        parent,
        action,
        runtime,
        scorer,
        verifier,
        reference_sha256=digest(reference) if reference is not None else None,
    )


def select_candidate(candidates: list[Candidate]) -> Candidate | None:
    """Local proposal policy, not an implementation of trajectory MH sampling."""
    eligible = [c for c in candidates if c.eligible]
    if not eligible:
        return None
    signatures = {
        (
            c.parent_checkpoint_id,
            c.score.model_id,
            c.score.backend_id,
            c.score.fixture_only,
        )
        for c in eligible
    }
    if len(signatures) != 1:
        raise BoundaryError("Cannot rank different checkpoints or score backends")
    return max(eligible, key=lambda c: c.score.mean_logprob)
