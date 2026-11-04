"""Map literal selector escaping to unique gold-collected IDs, without changing tests."""

import argparse
import json
from pathlib import Path
import shlex
import shutil
import time

from append_rewrite.terminus.docker_world import DockerWorld
from append_rewrite.terminus.production import tree
from append_rewrite.terminus.protocol import digest


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    spec = json.loads(a.spec.read_text())
    old = Path(spec["task_path"])
    contract = json.loads((old / "tests/contract.json").read_text())
    wanted = contract["test_ids"]
    parents = sorted({x.split("[", 1)[0] for x in wanted})
    sb = DockerWorld(spec["gold_template_id"], "cligym-test-selector-control")
    try:
        q = sb.run(
            "source /opt/miniconda3/bin/activate; conda activate testbed; "
            + shlex.join(["python", "-m", "pytest", "--collect-only", "-q", *parents]),
            cwd="/testbed",
            timeout=300,
        )
        (a.output / "gold-collection.log").write_text(q.stdout + q.stderr)
        if q.exit_code:
            raise ValueError("Gold tests could not be collected")
        collected = [
            x.strip()
            for x in q.stdout.splitlines()
            if x.startswith("tests/") and "::" in x
        ]
    finally:
        sb.kill()
    mapping = {}
    for requested in wanted:
        matches = [
            x for x in collected if x.replace("\\", "") == requested.replace("\\", "")
        ]
        if len(matches) != 1:
            raise ValueError("Selector mapping is missing or ambiguous")
        mapping[requested] = matches[0]
    if len(set(mapping.values())) != len(wanted):
        raise ValueError("Selector mapping collapsed distinct cases")
    task = a.output / "task"
    shutil.copytree(old, task)
    contract.update(
        test_ids=list(mapping.values()),
        explicit_pytest_argv=[
            "/opt/miniconda3/envs/testbed/bin/python",
            "-m",
            "pytest",
            "--disable-warnings",
            "--color=no",
            "--tb=no",
            "--verbose",
            *mapping.values(),
        ],
    )
    (task / "tests/contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    spec.update(
        unit_id=spec["unit_id"] + "-selectors-v2",
        task_path=str(task),
        task_manifest=tree(task),
        instruction_path=str(task / "instruction.md"),
    )
    spec["identity"] = digest(spec)
    (a.output / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    (a.output / "selector-binding.json").write_text(
        json.dumps(
            {
                "source_spec": str(a.spec),
                "mapping": mapping,
                "new_model_requests": 0,
                "test_functions_unchanged": True,
                "source_instruction_unchanged": True,
                "created_at": time.time(),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
