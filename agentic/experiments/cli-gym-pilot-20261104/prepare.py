"""Pin public CLI-Gym rows and Docker worlds; no model requests."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import textwrap
import threading

from append_rewrite.terminus.production import tree
from append_rewrite.terminus.protocol import digest
from append_rewrite.terminus.docker_world import checked, DockerWorld


def dump(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def test_ids(script):
    body = re.search(r"cat > tester.py <<EOF\n(.*?)\nEOF", script, re.S).group(1)
    for node in ast.walk(ast.parse(body)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_and_log"
        ):
            command = ast.literal_eval(node.args[0])
            return [x for x in shlex.split(command) if "::" in x]
    raise ValueError("No explicit pytest test IDs")


def prepare(row, index, output):
    unit = output / (f"row-{index:04d}")
    unit.mkdir(mode=0o700)
    dump(unit / "original-row.json", row)
    recipe = row["dockerfile"]
    base = re.search(r"^FROM\s+(\S+)", recipe, re.M).group(1)
    if re.search(r"^COPY\s+(?!<<)", recipe, re.M):
        raise ValueError("Unpublished build-context file")
    started = time.monotonic()
    with (unit / "pull.log").open("wb") as log:
        subprocess.run(
            ["docker", "pull", base], check=True, stdout=log, stderr=log, timeout=900
        )
    image = json.loads(checked("image", "inspect", base))[0]
    pinned = image["RepoDigests"][0]
    frozen = re.sub(r"^FROM\s+\S+", "FROM " + pinned, recipe, count=1, flags=re.M)
    (unit / "Dockerfile").write_text(frozen)
    tag = "append-rewrite/cligym:" + hashlib.sha256(frozen.encode()).hexdigest()[:16]
    with (unit / "build.log").open("wb") as log:
        subprocess.run(
            ["docker", "build", "-t", tag, str(unit)],
            check=True,
            stdout=log,
            stderr=log,
            timeout=1800,
            env={**__import__("os").environ, "DOCKER_BUILDKIT": "1"},
        )
    bad_id = json.loads(checked("image", "inspect", tag))[0]["Id"]
    task = unit / "task"
    tests = task / "tests"
    tests.mkdir(parents=True)
    text = row["task_yaml"].partition("instruction: |")[2]
    text = re.split(r"\nauthor_(?:email|name):", text, maxsplit=1)[0]
    if not text.strip():
        raise ValueError("Missing original instruction")
    (task / "instruction.md").write_text(textwrap.dedent(text).strip() + "\n")
    (task / "original-task.yaml").write_text(row["task_yaml"])
    (tests / "run-original.sh").write_text(row["run_tests"])
    ids = test_ids(row["run_tests"])
    if not ids:
        raise ValueError("No scoring targets")
    dump(
        tests / "contract.json",
        {
            "test_ids": ids,
            "timeout_sec": 3000,
            "original_run_tests_sha256": hashlib.sha256(
                row["run_tests"].encode()
            ).hexdigest(),
        },
    )
    sb = DockerWorld(bad_id, "cligym-freeze-public-tests")
    try:
        (tests / "original-tests.tgz").write_bytes(
            checked("exec", sb.sandbox_id, "tar", "czf", "-", "-C", "/testbed", "tests")
        )
    finally:
        sb.kill()
    (unit / "state").mkdir()
    spec = {
        "unit_id": f"cligym-row-{index:04d}",
        "environment_backend": "docker",
        "template_id": bad_id,
        "gold_template_id": image["Id"],
        "task_path": str(task),
        "task_manifest": tree(task),
        "state_path": str(unit / "state"),
        "state_manifest": {},
        "instruction_path": str(task / "instruction.md"),
        "cwd": "/testbed",
        "artifacts": ["/app/output/"],
        "restore_reset_paths": ["/app/output/"],
        "solver_network": "bridge",
        "source": {
            "kind": "cli-gym",
            "row_index": index,
            "task_id": row["task_id"],
            "base_digest": pinned,
            "dataset_revision": "552945c5aaf07d9715549a798c98ee13bb5b7f06",
        },
    }
    spec["episode_timeout_sec"] = float(
        re.search(r"max_agent_timeout_sec:\s*([\d.]+)", row["task_yaml"]).group(1)
    )
    spec["identity"] = digest(spec)
    dump(unit / "spec.json", spec)
    dump(
        unit / "preparation.json",
        {
            "elapsed_sec": time.monotonic() - started,
            "recipe_sha256": hashlib.sha256(recipe.encode()).hexdigest(),
            "base_image": image["Id"],
            "broken_image": bad_id,
            "test_count": len(ids),
            "new_model_requests": 0,
        },
    )
    return {
        "unit_id": spec["unit_id"],
        "lane": f"lane-{index % 4}",
        "spec_path": str(unit / "spec.json"),
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--rows", type=Path, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    wanted = [1, 15, 16, 87, 29, 46]
    rows = {
        x["row_idx"]: x["row"]
        for f in a.rows
        for x in json.loads(f.read_text())["rows"]
    }
    plan, held = [], []
    lock = threading.Lock()
    dump(a.output / "plan.json", {"units": []})
    # Parallel projects share base pulls, so prepare one case per project first.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    groups = [[1, 15], [16, 87], [29, 46]]

    def group(indices):
        for i in indices:
            try:
                item = prepare(rows[i], i, a.output)
                with lock:
                    plan.append(item)
                    dump(a.output / "plan.json", {"units": plan})
            except Exception as e:
                with lock:
                    held.append(
                        {
                            "row_index": i,
                            "error_type": type(e).__name__,
                            "message": str(e)[:500],
                        }
                    )
            with lock:
                dump(
                    a.output / "progress.json",
                    {"requested_rows": wanted, "prepared": len(plan), "held": held},
                )

    with ThreadPoolExecutor(3) as pool:
        for f in as_completed([pool.submit(group, x) for x in groups]):
            f.result()
    dump(
        a.output / "complete.json",
        {
            "prepared": len(plan),
            "held": held,
            "plan_sha256": hashlib.sha256(
                (a.output / "plan.json").read_bytes()
            ).hexdigest(),
        },
    )


if __name__ == "__main__":
    main()
