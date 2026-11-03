"""Bind an evaluator's batch input to the already published task configuration.

No scoring rule changes; preserve inherited regression fixtures and originals.
"""

import json
from pathlib import Path
import shutil
from append_rewrite.collect import sha
from .production_sources import ref_path
from .production import tree


def event_binding(spec, output):
    if spec["source"]["kind"] != "foundry" or spec["lane"] != "foundry-event":
        return spec
    order = json.loads(Path(spec["source"]["order_path"]).read_text())
    profile = json.loads(ref_path(order["profile"]).read_text())
    argv = profile["harbor_worker"]["fresh_grader_argv"]
    published = Path(argv[argv.index("--batch") + 1])
    expected = spec["state_manifest"]["work/netting-routes.json"]["sha256"]
    if sha(published) != expected:
        raise ValueError("Evaluator batch input does not match published initial state")
    old = Path(spec["task_path"])
    if sha(old / "tests/fixtures/netting-routes.json") == expected:
        return spec
    wrapper = (old / "tests/grade.py").read_text()
    already = old / "tests/published-netting-routes.json"
    if (
        already.is_file()
        and sha(already) == expected
        and "'/tests/published-netting-routes.json'" in wrapper
    ):
        return spec
    target = "'/tests/fixtures/netting-routes.json'"
    if wrapper.count(target) != 1:
        raise ValueError("Unrecognized evaluator batch binding")
    task = output / "derived-task"
    shutil.copytree(old, task)
    (task / "tests/grade.py").write_text(
        wrapper.replace(target, "'/tests/published-netting-routes.json'")
    )
    shutil.copy2(published, task / "tests/published-netting-routes.json")
    updated = dict(spec, task_path=str(task), task_manifest=tree(task))
    updated["verifier_revision"] = {
        "kind": "published_batch_fixture_binding.v1",
        "original_task_path": str(old),
        "source_public_config_sha256": expected,
        "changed_private_files": [
            "tests/grade.py",
            "tests/published-netting-routes.json",
        ],
        "scoring_rules_changed": False,
        "inherited_fixture_preserved": True,
        "instruction_sha256_unchanged": sha(old / "instruction.md")
        == sha(task / "instruction.md"),
    }
    return updated
