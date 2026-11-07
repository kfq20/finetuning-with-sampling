"""Owned Docker worlds for tasks that repair state outside /app.

No daemon changes, host mounts, Docker socket, privileged containers or credential
environment forwarding. Full filesystem snapshots retain global package repairs.
"""

import json
from pathlib import Path
import shlex
import subprocess
import tempfile
from types import SimpleNamespace
import uuid
import hashlib
import re


def docker(*args, timeout=300, data=None):
    return subprocess.run(
        ["docker", *map(str, args)], input=data, capture_output=True, timeout=timeout
    )


def checked(*args, **kwargs):
    r = docker(*args, **kwargs)
    if r.returncode:
        raise RuntimeError(
            "DockerOperationFailed: " + r.stderr.decode(errors="replace")[-1000:]
        )
    return r.stdout


def judge_tests(log, wanted, canary):
    statuses = dict(
        re.findall(
            r"^(.+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)(?:\s|$)", log, re.M
        )
    )
    passed = all(statuses.get(node) == "PASSED" for node in wanted)
    trustworthy = canary.exit_code == 1 and "1 failed" in canary.stdout
    return passed and trustworthy, statuses, trustworthy


class DockerWorld:
    def __init__(self, image, owner, *, network="none"):
        self.sandbox_id = (
            checked(
                "run",
                "-d",
                "--network",
                network,
                "--cpus",
                "4",
                "--memory",
                "8g",
                "--pids-limit",
                "512",
                "--label",
                "append-rewrite.study=cli-gym-pilot-20261104",
                "--label",
                "append-rewrite.owner=" + owner,
                "--entrypoint",
                "/bin/bash",
                image,
                "-c",
                "while true; do sleep 3600; done",
            )
            .decode()
            .strip()
        )
        self.commands = SimpleNamespace(run=self.run)
        self.files = SimpleNamespace(write=self.write, read=self.read)

    def set_timeout(self, value):
        # Lifetime is owned by the controller's existing episode deadline/finally.
        self.requested_timeout = value

    def run(self, text, *, user="root", cwd=None, timeout=300, envs=None, **kwargs):
        argv = ["exec", "-u", user]
        if cwd:
            argv += ["-w", cwd]
        for k, v in (envs or {}).items():
            argv += ["-e", str(k) + "=" + str(v)]
        r = docker(*argv, self.sandbox_id, "/bin/bash", "-lc", text, timeout=timeout)
        return SimpleNamespace(
            exit_code=r.returncode,
            stdout=r.stdout.decode(errors="replace"),
            stderr=r.stderr.decode(errors="replace"),
        )

    def write(self, path, content, **kwargs):
        self.run("mkdir -p " + shlex.quote(str(Path(path).parent)))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "payload"
            f.write_bytes(content.encode() if isinstance(content, str) else content)
            checked("cp", f, self.sandbox_id + ":" + path)

    def read(self, path, *, format="text", **kwargs):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "payload"
            checked("cp", self.sandbox_id + ":" + path, f)
            raw = f.read_bytes()
        return raw if format == "bytes" else raw.decode()

    def kill(self):
        checked("rm", "-f", self.sandbox_id)

    def snapshot(self, dest):
        name = "append-rewrite/cligym-snapshot:" + uuid.uuid4().hex
        # Newer CLIs mix deprecation notices into commit stdout. Resolve the
        # immutable ID from structured inspect instead of trusting display text.
        checked("commit", self.sandbox_id, name)
        image = json.loads(checked("image", "inspect", name))[0]["Id"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("Docker commit did not resolve an immutable image")
        record = {
            "storage_format": "docker-full-filesystem-image.v1",
            "image_id": image,
            "image_tag": name,
            "container_id": self.sandbox_id,
            "process_memory_restored": False,
        }
        raw = json.dumps(record, sort_keys=True).encode()
        Path(dest).write_bytes(raw)
        return {
            **record,
            "snapshot_path": str(dest),
            "archive_sha256": hashlib.sha256(raw).hexdigest(),
        }

    def grade(self, task):
        """Grade on the controller; a broken target Python cannot erase reward."""
        contract = json.loads((task / "tests/contract.json").read_text())
        self.write(
            "/tests/run-original.sh", (task / "tests/run-original.sh").read_bytes()
        )
        self.write(
            "/tests/original-tests.tgz",
            (task / "tests/original-tests.tgz").read_bytes(),
        )
        from .cli_contract import safe_test_paths
        frozen_paths = safe_test_paths(contract.get('frozen_test_paths', ['tests']))
        reset = self.run(
            "rm -rf -- " + shlex.join(['/testbed/' + x for x in frozen_paths])
            + "; tar xzf /tests/original-tests.tgz -C /testbed; rm -f /test.log"
        )
        if reset.exit_code:
            raise RuntimeError("FrozenTestsRestoreFailed")
        if contract.get("explicit_pytest_argv"):
            q = self.run(
                "source /opt/miniconda3/bin/activate; conda activate testbed; "
                + shlex.join(contract["explicit_pytest_argv"]),
                cwd="/testbed",
                timeout=contract["timeout_sec"],
            )
            log = q.stdout + q.stderr
        else:
            q = self.run(
                "bash /tests/run-original.sh",
                cwd="/testbed",
                timeout=contract["timeout_sec"],
            )
            exists = self.run("test -f /test.log")
            if exists.exit_code and exists.stderr:
                raise RuntimeError("GradingLogTransportFailed")
            log = self.read("/test.log") if exists.exit_code == 0 else ""
        wanted = contract["test_ids"]
        self.write(
            "/tests/canary.py", "def test_expected_failure():\n    assert False\n"
        )
        canary = self.run(
            "/opt/miniconda3/envs/testbed/bin/python -m pytest -p no:cacheprovider -q /tests/canary.py",
            cwd="/testbed",
            timeout=120,
        )
        passed, statuses, trustworthy = judge_tests(log, wanted, canary)
        return {
            "reward": float(passed and trustworthy),
            "details": {
                "expected_tests": len(wanted),
                "passed_tests": sum(statuses.get(n) == "PASSED" for n in wanted),
                "missing_tests": [n for n in wanted if n not in statuses],
                "statuses": statuses,
                "canary_expected_failure": trustworthy,
                "test_script_exit": q.exit_code,
                "test_log": log,
            },
        }


def snapshot_world(path, owner):
    image = json.loads(Path(path).read_text())["image_id"]
    if not image.startswith("sha256:") or len(image) != 71:
        raise ValueError("Expected local immutable Docker image ID")
    return DockerWorld(image, owner)
