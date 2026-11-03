"""Publish hash-bound no-model admissions; never dispatch or retry a solver."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time
from append_rewrite.collect import sha
from .production import control_binding, dump


def publish(selection, output):
    items = json.loads(Path(selection["census"]).read_text())["rows"]
    result = []
    for item in items:
        key = item["unit_id"]
        current = None
        for root in selection["review_roots"]:
            directory = Path(root) / "units" / key
            if (directory / "status.json").exists():
                current = directory
        if current is None:
            result.append({"unit_id": key, "lane": item["lane"], "status": "pending"})
            continue
        status = json.loads((current / "status.json").read_text())
        record = {
            "unit_id": key,
            "lane": item["lane"],
            "status": status["phase"],
            "review_path": str(current),
        }
        rp = current / "receipt.json"
        if rp.exists():
            receipt = json.loads(rp.read_text())
            if receipt.get("passed"):
                spec = json.loads((current / "spec.json").read_text())
                cert = {
                    "passed": True,
                    "control_binding": control_binding(spec),
                    "initial": receipt["initial"],
                    "legal": receipt["legal"],
                    "original_report_path": str(rp),
                    "original_report_sha256": sha(rp),
                    "new_model_requests": 0,
                    "original_grader_unchanged": True,
                }
                dest = output / "admissions" / key
                dest.mkdir(parents=True, exist_ok=True)
                cp = dest / "certificate.json"
                dump(cp, cert)
                spec["preflight_certificate"] = {"path": str(cp), "sha256": sha(cp)}
                dump(dest / "spec.json", spec)
                record.update(
                    status="passed",
                    admission_spec=str(dest / "spec.json"),
                    certificate_sha256=sha(cp),
                )
            elif receipt.get("initial", {}).get("reward") == 1:
                record.update(
                    status="initial_already_satisfies_excluded", training_admitted=False
                )
        result.append(record)
    report = {
        "observed_at_epoch": time.time(),
        "counts": dict(Counter(x["status"] for x in result)),
        "rows": result,
        "new_model_requests": 0,
        "model_retries": 0,
    }
    dump(output / "report.json", report)
    return report


def alive(record):
    p = Path("/proc") / str(record["pid"])
    try:
        stat = (p / "stat").read_text()
        return stat[stat.rfind(")") + 2 :].split()[19] == record["start_ticks"]
    except OSError:
        return False


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--follow", action="store_true")
    a = p.parse_args()
    s = json.loads(a.selection.read_text())
    a.output.mkdir(parents=True, exist_ok=True)
    while True:
        report = publish(s, a.output)
        workers = [json.loads(Path(path).read_text()) for path in s["worker_launches"]]
        if not a.follow or not any(alive(x) for x in workers):
            dump(
                a.output / "publisher-finished.json",
                {
                    "at": time.time(),
                    "counts": report["counts"],
                    "new_model_requests": 0,
                },
            )
            print(json.dumps(report["counts"]))
            return
        time.sleep(15)


if __name__ == "__main__":
    main()
