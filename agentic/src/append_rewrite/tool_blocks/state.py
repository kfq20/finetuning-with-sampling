"""Executable file-only fixture adapter. Not a replacement for native CC tools.

Production adapters must declare additional process/database state capabilities.
No shell commands, models, network access or credentials are used here.
"""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from .trace import BoundaryError, encode, digest

FILE_SCOPE = "file_contents_modes_directories"
FIXTURE_ENV = "directory-read-write-fixture.v1"


@dataclass(frozen=True)
class StateRef:
    uri: str
    sha256: str
    environment_id: str
    scopes: tuple[str, ...]

    def same_content(self, other: StateRef) -> bool:
        return (self.sha256, self.environment_id, self.scopes) == (
            other.sha256,
            other.environment_id,
            other.scopes,
        )


@dataclass(frozen=True)
class Execution:
    branch_id: str
    before_sha256: str
    after: StateRef
    action_sha256: str
    results_json: str

    @property
    def results(self) -> list[dict]:
        return json.loads(self.results_json)


class FileStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "blobs").mkdir(exist_ok=True, mode=0o700)
        (self.root / "states").mkdir(exist_ok=True, mode=0o700)

    @staticmethod
    def manifest(project: Path) -> tuple[dict, dict[str, bytes]]:
        entries, blobs = {}, {}
        if project.is_symlink():
            raise BoundaryError("Fixture root cannot be a symlink")
        for path in sorted(project.rglob("*")):
            if path.is_symlink():
                raise BoundaryError("Symlink state requires a dedicated adapter")
            meta = {"mode": path.stat().st_mode & 0o777}
            if path.is_file():
                data = path.read_bytes()
                key = hashlib.sha256(data).hexdigest()
                blobs[key] = data
                meta.update(kind="file", sha256=key)
            elif path.is_dir():
                meta["kind"] = "directory"
            else:
                raise BoundaryError("Nonregular state needs a dedicated adapter")
            entries[path.relative_to(project).as_posix()] = meta
        return {
            "schema": "file-state.v1",
            "environment_id": FIXTURE_ENV,
            "root_mode": project.stat().st_mode & 0o777,
            "entries": entries,
        }, blobs

    def capture(self, project: Path) -> StateRef:
        manifest, blobs = self.manifest(project)
        for key, data in blobs.items():
            path = self.root / "blobs" / key
            if path.exists():
                if hashlib.sha256(path.read_bytes()).hexdigest() != key:
                    raise BoundaryError("Corrupt existing state blob")
            else:
                path.write_bytes(data)
                path.chmod(0o600)
        key = digest(manifest)
        target = self.root / "states" / (key + ".json")
        if target.exists() and target.read_text() != encode(manifest):
            raise BoundaryError("Corrupt existing state manifest")
        if not target.exists():
            target.write_text(encode(manifest))
            target.chmod(0o600)
        return StateRef(str(target), key, FIXTURE_ENV, (FILE_SCOPE,))

    def restore(self, state: StateRef, target: Path) -> None:
        if state.environment_id != FIXTURE_ENV or state.scopes != (FILE_SCOPE,):
            raise BoundaryError("Unsupported fixture state identity/capabilities")
        source = Path(state.uri).resolve()
        if source.parent != self.root / "states":
            raise BoundaryError("State manifest is outside this store")
        manifest = json.loads(source.read_text())
        if (
            digest(manifest) != state.sha256
            or manifest["environment_id"] != FIXTURE_ENV
        ):
            raise BoundaryError("State manifest identity changed")
        # Validate every reference and blob BEFORE creating a branch.
        for name, meta in manifest["entries"].items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or name in ("", "."):
                raise BoundaryError("Unsafe state path")
            if meta["kind"] == "file":
                if (
                    not isinstance(meta["sha256"], str)
                    or len(meta["sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in meta["sha256"])
                ):
                    raise BoundaryError("Unsafe blob identity")
                data = (self.root / "blobs" / meta["sha256"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != meta["sha256"]:
                    raise BoundaryError("State blob identity changed")
            elif meta["kind"] != "directory":
                raise BoundaryError("Unsupported state entry")
        target.mkdir(parents=False, exist_ok=False, mode=0o700)
        directories = []
        for name, meta in manifest["entries"].items():
            path = target / name
            if meta["kind"] == "directory":
                path.mkdir(parents=True, exist_ok=True)
                directories.append((path, meta["mode"]))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((self.root / "blobs" / meta["sha256"]).read_bytes())
                path.chmod(meta["mode"])
        for path, mode in sorted(
            directories, key=lambda x: len(x[0].parts), reverse=True
        ):
            path.chmod(mode)
        target.chmod(manifest["root_mode"])
        if digest(self.manifest(target)[0]) != state.sha256:
            raise BoundaryError("Restored state does not match snapshot")


class DirectorySession:
    """Owned fixture files only; unsupported native tools fail closed."""

    def __init__(self, root: Path, store: FileStore, branch_id: str):
        self.root, self.store, self.branch_id = root, store, branch_id

    def snapshot(self) -> StateRef:
        return self.store.capture(self.root)

    def close(self) -> None:
        # No service process to terminate; keep owned branch evidence for review.
        pass

    def _path(self, raw: str) -> Path:
        if not isinstance(raw, str) or not raw:
            raise BoundaryError("Missing fixture file path")
        p = Path(raw)
        if p.is_absolute() or ".." in p.parts:
            raise BoundaryError(
                "Fixture tools require relative paths inside branch root"
            )
        path = self.root / p
        if any(x.is_symlink() for x in [path, *path.parents] if x != self.root.parent):
            raise BoundaryError("Fixture tool cannot traverse symlinks")
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise BoundaryError("Path escapes branch")
        return path

    def execute(self, calls: list[dict]) -> Execution:
        # Read-only batches commute. Mixed writes may have ordering dependencies;
        # do not pretend this fixture implements native parallel scheduling.
        if len(calls) > 1 and any(c["name"] != "Read" for c in calls):
            raise BoundaryError("Parallel write/mixed batch requires a native adapter")
        for call in calls:
            allowed = {"Read": {"file_path"}, "Write": {"file_path", "content"}}
            if (
                call["name"] not in allowed
                or set(call["input"]) != allowed[call["name"]]
            ):
                raise BoundaryError(
                    "Unsupported fixture tool/schema; no shell fallback"
                )
            self._path(call["input"]["file_path"])
        before = self.snapshot()
        results = []
        for call in calls:
            path = self._path(call["input"]["file_path"])
            failed = False
            try:
                if call["name"] == "Read":
                    content = path.read_text()
                else:
                    if not isinstance(call["input"]["content"], str):
                        raise TypeError("Write content must be text")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(call["input"]["content"])
                    content = "File written"
            except (OSError, UnicodeError, TypeError) as exc:
                content, failed = "Tool failed: " + type(exc).__name__, True
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": content,
                    "is_error": failed,
                }
            )
        return Execution(
            self.branch_id,
            before.sha256,
            self.snapshot(),
            digest(calls),
            encode(results),
        )


class DirectoryRuntime:
    """Each fork is a new physical directory, never the parent workspace."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.store = FileStore(self.root / "store")
        (self.root / "branches").mkdir(mode=0o700)

    def fork(self, state: StateRef, branch_id: str) -> DirectorySession:
        if not branch_id.isalnum():
            raise BoundaryError("Unsafe branch ID")
        target = self.root / "branches" / branch_id
        self.store.restore(state, target)
        return DirectorySession(target, self.store, branch_id)
