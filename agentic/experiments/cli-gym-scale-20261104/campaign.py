"""Finite CLI-Gym waves until500 admitted trajectories or source/storage exhaustion.

One task attempt per source row. Existing wave1 is observed, never relaunched.
Each later wave gets its own explicit frozen selection and exclusive launch.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen

REVISION = "552945c5aaf07d9715549a798c98ee13bb5b7f06"


def dump(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def get(url):
    # Public immutable data only; never used for model generation retries.
    for attempt in range(3):
        try:
            with urlopen(url, timeout=90) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def catalog(root):
    target = root / "catalog"
    target.mkdir(exist_ok=True)
    meta_url = "https://huggingface.co/api/datasets/LiberCoders/CLI-Gym"
    if get(meta_url)["sha"] != REVISION:
        raise ValueError("Dataset revision changed; explicit new freeze required")
    pages = []
    for offset in range(0, 1655, 50):
        path = target / f"rows-{offset:04d}.json"
        if not path.exists():
            if offset < 100:
                data = json.loads((root / "input" / (
                    "rows-0-50.json" if offset == 0 else "rows-50-100.json"
                )).read_text())
            else:
                data = get("https://datasets-server.huggingface.co/rows?" + urlencode({
                    "dataset": "LiberCoders/CLI-Gym", "config": "default",
                    "split": "train", "offset": offset, "length": 50,
                    "revision": REVISION,
                }))
            if (data["num_rows_total"] != 1655 or data.get("partial")
                or [x["row_idx"] for x in data["rows"]] != list(range(offset, min(offset + 50, 1655)))
                or any(x.get("truncated_cells") for x in data["rows"])):
                raise ValueError("Incomplete CLI-Gym source page")
            dump(path, data)
        pages.append(path)
    if get(meta_url)["sha"] != REVISION:
        raise ValueError("Dataset changed while freezing source pages")
    dump(target / "manifest.json", {
        "revision": REVISION, "rows": 1655,
        "pages": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in pages},
        "new_model_requests": 0,
    })
    return pages


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--fleet-config", type=Path)
    a = p.parse_args()
    root = a.root
    if a.workers < 1:
        raise ValueError('Positive worker capacity required')
    os.environ['APPEND_REWRITE_STUDENT_CAPACITY'] = str(a.workers)
    source = Path(__file__).resolve().parents[3]
    entries = source / "agentic/experiments/cli-gym-pilot-20261104"
    publish = runpy.run_path(str(Path(__file__).with_name("collect.py")))["publish"]
    # One owner across current and later waves. No restart of existing dispatch.
    import fcntl
    lock = (root / "campaign.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    prior = json.loads((root / 'campaign-progress.json').read_text()) if a.resume else None
    runs = [Path(x) for x in prior['runs']] if prior else [root / "pilot-evidence", root / "run"]
    pages = catalog(root)

    def refresh(phase, **extra):
        manifest = publish(runs, root / "campaign-sft")
        dump(root / "campaign-progress.json", {
            "checked_at": time.time(), "phase": phase,
            "valid_sft": manifest["valid_trajectories"], "target": 500,
            "requested_range": [500, 1000], "runs": list(map(str, runs)), **extra,
        })
        return manifest["valid_trajectories"]

    current = Path(prior['wave']) if prior and prior.get('wave') else root
    while not (current / "run/coordinator-finished.json").exists():
        refresh("existing_wave_running", wave=str(current))
        if (root / "USER_STOP.json").exists() or (current / "run/STOP_PROVIDER").exists():
            refresh("stopped"); return
        if a.resume:
            identity = json.loads((current / 'production-launch.json').read_text())
            proc = Path('/proc') / str(identity['pid']) / 'stat'
            fields = proc.read_text().split(') ')[1].split() if proc.exists() else []
            if not fields or fields[0] == 'Z' or fields[19] != identity['start_ticks']:
                refresh('current_coordinator_missing', wave=str(current)); return
        time.sleep(15)
    first_offset = int(current.name.split('-')[1]) + 100 if current != root else 100
    for offset in range(first_offset, 1655, 100):
        if (current / "run/STOP_PROVIDER").exists():
            refresh("provider_hold"); return
        if refresh("between_waves") >= 500:
            refresh("target_reached"); return
        if (root / "USER_STOP.json").exists():
            refresh("user_stopped"); return
        # Disk safety is a physical admission gate, not a model/token budget.
        import shutil
        if shutil.disk_usage(root).free < 20 * 1024**3:
            refresh("storage_hold"); return
        wave = root / f"wave-{offset:04d}"
        wave.mkdir(mode=0o700, exist_ok=False)
        indices = list(range(offset, min(offset + 100, 1655)))
        selected_pages = [x for x in pages if offset <= int(x.stem.split('-')[1]) < offset + 100]
        dump(wave / "active_runtime_selection.json", {
            "source_root": str(source), "source_commit": a.source_commit,
            "dataset_revision": REVISION, "source_rows": indices,
            "automatic_paid_retry": False, "student_target": a.workers,
            "worker_capacity": a.workers, "queue_policy": "shared",
            "score_prefill_concurrency": 2, "candidates_per_block": 8,
            "fleet_config_sha256": hashlib.sha256(a.fleet_config.read_bytes()).hexdigest() if a.fleet_config else None,
        })
        with (wave / "preparation.log").open("xb") as log:
            prep = subprocess.Popen([
                sys.executable, str(entries / "prepare.py"), "--rows", *map(str, selected_pages),
                "--output", str(wave / "prepared"), "--indices", *map(str, indices),
                "--canonicalize-selectors", "--storage-root", str(root),
            ], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        with (wave / "pipeline.log").open("xb") as log:
            command = [
                sys.executable, str(entries / "launch.py"), "--root", str(wave),
                "--legacy-root", str(root / "support"), "--prepared", str(wave / "prepared"),
                "--source-commit", a.source_commit, "--skip-comparison",
                "--workers", str(a.workers),
            ]
            if a.fleet_config:
                command += ['--fleet-config', str(a.fleet_config)]
            pipeline = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        runs.append(wave / "run")
        dump(wave / "controllers.json", {"preparation_pid": prep.pid, "pipeline_pid": pipeline.pid,
              "started_at": time.time(), "source_commit": a.source_commit})
        while pipeline.poll() is None:
            refresh("wave_running", wave=str(wave))
            time.sleep(15)
        prep.wait()
        if pipeline.returncode or not (wave / "run/coordinator-finished.json").exists():
            refresh("wave_infrastructure_hold", wave=str(wave), exit_code=pipeline.returncode); return
        if (wave / "run/STOP_PROVIDER").exists():
            refresh("provider_hold", wave=str(wave)); return
        current = wave
    refresh("source_pool_exhausted")


if __name__ == "__main__":
    main()
