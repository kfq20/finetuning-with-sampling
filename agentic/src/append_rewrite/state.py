"""Bind pre-append state to published restore manifests, never future artifacts."""

from __future__ import annotations
import json
from pathlib import Path
import tomllib
from .collect import sha


def plan(task: Path, parent_native: Path):
    binding = json.loads((task / "runtime-binding.json").read_text())
    public = task / "environment/public"
    manifests = binding.get("restore_manifests")
    if not manifests:
        root = binding.get("restore_root")
        if not root:
            config = tomllib.loads((task / "task.toml").read_text())
            root = config.get("environment", {}).get("workdir")
        if not root:
            raise ValueError("restore_root_unbound")
        manifest = binding.get("checkpoint_manifest")
        if not manifest:
            raise ValueError("checkpoint_manifest_missing")
        manifests = {root: manifest}
    parent_trial = next(
        (p for p in parent_native.parents if (p / "result.json").is_file()), None
    )
    sources = [p for p in public.rglob("*") if p.is_file() and not p.is_symlink()]
    if parent_trial:
        sources += [
            p
            for p in (parent_trial / "artifacts/app").rglob("*")
            if p.is_file() and not p.is_symlink()
        ]
    index = {}
    for p in sources:
        index.setdefault(sha(p), p)
    mapped = {}
    for root, files in manifests.items():
        target_root = Path(root)
        if not target_root.is_relative_to("/app"):
            raise ValueError("restore_outside_app")
        for name, meta in files.items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("unsafe_restore_name")
            target = str((target_root / name).relative_to("/app"))
            source = index.get(meta["sha256"])
            if source is None:
                raise ValueError("checkpoint_source_missing:" + target)
            mapped[target] = (source, meta["mode"])
    return mapped
