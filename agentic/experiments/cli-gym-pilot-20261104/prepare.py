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
import shutil

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


def prepare(row, index, output, *, canonicalize_selectors=False,
            build_network='none', repair_contract=False, apt_mirror=False, bounded_pytest=False):
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
    if apt_mirror and 'apt-get' in recipe:
        # Change prerequisite download transport before the original fault recipe.
        # Solver networking and all original RUN fault commands stay unchanged.
        prelude = ('RUN for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.list '
                   '/etc/apt/sources.list.d/*.sources; do [ ! -f "$f" ] || '
                   "sed -i -E 's#https?://(archive|security)\\.ubuntu\\.com/ubuntu#"
                   "https://repo.huaweicloud.com/ubuntu#g' \"$f\"; done\n")
        frozen = frozen.replace('FROM ' + pinned, 'FROM ' + pinned + '\n' + prelude, 1)
    (unit / "Dockerfile").write_text(frozen)
    tag = "append-rewrite/cligym:" + hashlib.sha256(frozen.encode()).hexdigest()[:16]
    with (unit / "build.log").open("wb") as log:
        subprocess.run(
            ["docker", "build", "--network", build_network, "-t", tag, str(unit)],
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
    ids = test_ids(row["run_tests"]) if not repair_contract else []
    frozen_paths = ['tests']
    if repair_contract:
        from append_rewrite.terminus.cli_contract import published_selectors, test_roots, resolve_selectors, PYTEST_RESOURCES
        ids = published_selectors(row['run_tests'])
        requested = list(ids)
        gold = DockerWorld(image['Id'], 'cligym-contract-collection')
        serial_xdist = False
        try:
            if bounded_pytest:
                installed = gold.run('/opt/miniconda3/envs/testbed/bin/python -c '
                    + shlex.quote("import importlib.util; print(int(importlib.util.find_spec('xdist') is not None))"), timeout=60)
                if installed.exit_code:
                    raise ValueError('Gold test runtime could not be inspected')
                serial_xdist = installed.stdout.strip() == '1'
            parents = sorted({x.split('[', 1)[0] for x in ids})
            q = gold.run('source /opt/miniconda3/bin/activate; conda activate testbed; '
                         + shlex.join(['python', '-m', 'pytest', '--collect-only', '-q', *parents]),
                         cwd='/testbed', timeout=600,
                         envs=PYTEST_RESOURCES if bounded_pytest else None)
            (unit / 'gold-collection.log').write_text(q.stdout + q.stderr)
            if q.exit_code:
                raise ValueError('Gold tests could not be collected')
            collected = [x.strip() for x in q.stdout.splitlines()
                         if '::' in x and not x.startswith((' ', '<', '='))]
            # An empty published selector list means full-suite pytest, not no tests.
            ids = resolve_selectors(ids, collected) if ids else collected
            dump(unit / 'selector-resolution.json', {'requested': requested,
                 'resolved_test_ids': ids, 'new_model_requests': 0,
                 'rule': 'All children of class/function selectors; unique gold-ID aliases; no missing test dropped'})
            frozen_paths = test_roots(ids)
        finally:
            gold.kill()
    if not ids:
        raise ValueError("No scoring targets")
    contract = {
            "test_ids": ids,
            "timeout_sec": 3000,
            "original_run_tests_sha256": hashlib.sha256(row["run_tests"].encode()).hexdigest(),
        }
    if repair_contract:
        contract.update(frozen_test_paths=frozen_paths, explicit_pytest_argv=[
            '/opt/miniconda3/envs/testbed/bin/python', '-m', 'pytest', '--disable-warnings',
            '--color=no', '--tb=no', '--verbose', *ids])
        if bounded_pytest:
            from append_rewrite.terminus.cli_contract import bound_pytest_resources
            contract['explicit_pytest_argv'] = bound_pytest_resources(contract['explicit_pytest_argv'], serial_xdist=serial_xdist)
    dump(
        tests / "contract.json",
        contract,
    )
    sb = DockerWorld(image['Id'] if repair_contract else bad_id, "cligym-freeze-public-tests")
    try:
        (tests / "original-tests.tgz").write_bytes(
            checked("exec", sb.sandbox_id, "tar", "czf", "-", "-C", "/testbed", *frozen_paths)
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
        "solver_network": "none",
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
    spec_path = unit / "spec.json"
    if not repair_contract and canonicalize_selectors and any(re.search(r"[\\\"']", x) for x in ids):
        # Repair transport escaping before any paid attempt; assertions unchanged.
        import sys

        repaired = unit / "selector-transport"
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name("repair_test_ids.py")),
             "--spec", str(spec_path), "--output", str(repaired)],
            check=True,
        )
        spec_path = repaired / "spec.json"
        spec = json.loads(spec_path.read_text())
    dump(
        unit / "preparation.json",
        {
            "elapsed_sec": time.monotonic() - started,
            "recipe_sha256": hashlib.sha256(recipe.encode()).hexdigest(),
            "base_image": image["Id"],
            "broken_image": bad_id,
            "test_count": len(ids),
            "new_model_requests": 0,
            "build_network": build_network,
            "solver_network": "none",
            "repair_contract": repair_contract,
            "apt_prerequisite_mirror": 'https://repo.huaweicloud.com/ubuntu' if apt_mirror else None,
        },
    )
    return {
        "unit_id": spec["unit_id"],
        "lane": f"lane-{index % 4}",
        "spec_path": str(spec_path),
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--rows", type=Path, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--indices", type=int, nargs="+", default=[1, 15, 16, 87, 29, 46])
    p.add_argument("--canonicalize-selectors", action="store_true")
    p.add_argument("--storage-root", type=Path)
    p.add_argument('--build-network', choices=('none', 'host'), default='none')
    p.add_argument('--repair-contract', action='store_true')
    p.add_argument('--min-free-gib', type=int, default=20)
    p.add_argument('--apt-mirror', action='store_true')
    p.add_argument('--bounded-pytest', action='store_true')
    a = p.parse_args()
    a.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    wanted = a.indices
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

    grouped = {}
    for i in wanted:
        base = re.search(r"^FROM\s+(\S+)", rows[i]["dockerfile"], re.M).group(1)
        grouped.setdefault(base, []).append(i)
    groups = list(grouped.values())

    def group(indices):
        for i in indices:
            try:
                if a.storage_root and shutil.disk_usage(a.storage_root).free < a.min_free_gib * 1024**3:
                    raise RuntimeError("StorageAdmissionHold: no deletion or model retry")
                item = prepare(
                    rows[i], i, a.output,
                    canonicalize_selectors=a.canonicalize_selectors,
                    build_network=a.build_network, repair_contract=a.repair_contract, apt_mirror=a.apt_mirror,
                    bounded_pytest=a.bounded_pytest,
                )
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
