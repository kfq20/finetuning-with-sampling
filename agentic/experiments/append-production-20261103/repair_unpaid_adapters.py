"""Rebind only 404-before-inference units to their exact published adapters."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from append_rewrite.terminus.production import dump
from append_rewrite.terminus.production_sources import foundry


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    work = []
    for path in sorted(a.previous.glob("units/*/status.json")):
        status = json.loads(path.read_text())
        if (
            status.get("phase") != "hold"
            or status.get("error_type") != "SandboxException"
        ):
            continue
        key = path.parent.name
        if (
            "404: template not found"
            not in (a.previous / "logs" / (key + ".log")).read_text()
        ):
            continue
        if list(path.parent.glob("teacher/requests/request-*/intent.json")) or list(
            path.parent.glob("student/generation/turn-*/proposal-*/intent.json")
        ):
            raise ValueError("Paid model attempts must never be adapter-replayed")
        spec = json.loads((a.previous / "specs" / (key + ".json")).read_text())
        work.append((key, Path(spec["source"]["order_path"])))
    units, holds, repairs = [], [], []

    def prepare(item):
        key, order = item
        dest = a.output / "inputs" / key
        dest.mkdir(parents=True)
        try:
            return key, foundry(order, dest, []), None
        except Exception as e:
            return (
                key,
                None,
                {
                    "source": str(order),
                    "error_type": type(e).__name__,
                    "reason": str(e)[:300],
                },
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(prepare, x) for x in work]):
            key, item, error = future.result()
            if error:
                holds.append(error)
            else:
                units.append(item)
                repairs.append(
                    {
                        "predecessor_invalid_unit_id": key,
                        "unit_id": item["unit_id"],
                        "paid_model_attempts_before_repair": 0,
                    }
                )
            dump(
                a.output / "plan.json",
                {
                    "units": units,
                    "holds": holds,
                    "adapter_repairs": repairs,
                    "predecessor_root": str(a.previous),
                    "completed_model_replays": 0,
                },
            )
    dump(
        a.output / "summary.json",
        {"ready": len(units), "holds": len(holds), "source_records": len(work)},
    )
    print(
        json.dumps(
            {"ready": len(units), "holds": len(holds), "source_records": len(work)}
        )
    )


if __name__ == "__main__":
    main()
