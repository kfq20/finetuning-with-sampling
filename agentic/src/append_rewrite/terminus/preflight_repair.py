"""No-model repair of preflight adapters; preserve original submissions/scores."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
from append_rewrite.collect import sha
from .production import restore, apply_capture, dump
from append_rewrite import sandbox
import shlex
from .grader import observe
from .protocol import digest


def repaired_spec(spec, lane):
    spec = dict(spec)
    # Exact selective-reset semantics of the original legacy adapters.
    if lane == "legacy-cad":
        spec["restore_reset_paths"] = ["/app/output", "/app/stock", "/app/orders"]
    elif lane == "legacy-science":
        spec["restore_reset_paths"] = ["/app/project", "/app/submission"]
    elif lane == "legacy-audio":
        spec["restore_reset_paths"] = ["/app/output"]
    spec["preflight_adapter_identity"] = digest(
        {
            "identity": spec["identity"],
            "restore_reset_paths": spec.get("restore_reset_paths"),
            "reward_channels": ["reward.txt", "reward.json"],
        }
    )
    return spec


def run_one(item, args):
    started = time.time()
    out = args.output / "units" / item["unit_id"]
    out.mkdir(parents=True, exist_ok=False)
    spec_path = Path(item["spec_path"])
    original = json.loads(spec_path.read_text())
    spec = repaired_spec(original, item["lane"])
    from .fixture_binding import event_binding

    spec = event_binding(spec, out)
    if not spec.get("oracle_archive") and spec["source"]["kind"] == "foundry":
        from .control_sources import recover

        try:
            spec.update(recover(spec, out))
        except Exception as e:
            dump(
                out / "original-control-discovery-error.json",
                {"error_type": type(e).__name__, "message": str(e)[:400]},
            )
    recipe = None
    task = Path(spec["task_path"])
    if not spec.get("oracle_archive"):
        if (task / "solution/solve.sh").is_file():
            recipe = {
                "kind": "script",
                "path": str(task / "solution/solve.sh"),
                "sha256": sha(task / "solution/solve.sh"),
            }
        elif (
            item["lane"] == "legacy-science"
            and (task / "solution/reference.py").is_file()
        ):
            recipe = {
                "kind": "file",
                "path": str(task / "solution/reference.py"),
                "sha256": sha(task / "solution/reference.py"),
                "destination": "/app/submission/solver.py",
            }
        elif item["lane"] == "foundry-eigenmodes" and spec.get("original_controls_ref"):
            from .production_sources import ref_path

            ctrl = json.loads(ref_path(spec["original_controls_ref"]).read_text())
            if ctrl.get("control_evidence"):
                witness = (
                    ref_path(ctrl["control_evidence"]).parent / "third_order_witness.py"
                )
                if witness.is_file():
                    recipe = {
                        "kind": "file",
                        "path": str(witness),
                        "sha256": sha(witness),
                        "destination": "/app/submission/solver.py",
                    }
    if recipe:
        spec["private_legal_control_recipe"] = recipe
    dump(out / "spec.json", spec)
    dump(out / "status.json", {"phase": "initial_control"})
    try:
        sb = restore(
            spec,
            args,
            "preflight-repair-initial",
            template_id=spec.get("verifier_template_id"),
            install_runtime=False,
        )
        dump(out / "initial-sandbox.json", {"sandbox_id": sb.sandbox_id})
        try:
            initial = observe(sb, Path(spec["task_path"]), out / "initial")
        finally:
            sb.kill()
        if not spec.get("oracle_archive") and not recipe:
            dump(
                out / "receipt.json",
                {
                    "passed": False,
                    "reason": "original_legal_control_binding_required",
                    "initial": initial,
                    "source_original_outcome": spec["source"].get("original_outcome"),
                    "new_model_requests": 0,
                },
            )
            dump(out / "status.json", {"phase": "needs_original_control"})
            return
        if (
            spec.get("oracle_archive")
            and sha(Path(spec["oracle_archive"])) != spec["oracle_sha256"]
        ):
            raise ValueError("OriginalCaptureDrift")
        dump(out / "status.json", {"phase": "original_success_capture_control"})
        sb = restore(
            spec,
            args,
            "preflight-repair-original-capture",
            template_id=spec.get("verifier_template_id"),
            install_runtime=False,
        )
        dump(out / "legal-sandbox.json", {"sandbox_id": sb.sandbox_id})
        try:
            if spec.get("oracle_archive"):
                apply_capture(sb, Path(spec["oracle_archive"]), spec["artifacts"])
            else:
                source = Path(recipe["path"])
                if sha(source) != recipe["sha256"]:
                    raise ValueError("Original reference recipe drift")
                if recipe["kind"] == "script":
                    sandbox.upload(sb, task / "solution", "/solution")
                    result = sandbox.command(
                        sb,
                        "cd "
                        + shlex.quote(spec["cwd"])
                        + " && bash /solution/solve.sh",
                        user="root",
                        timeout=1800,
                    )
                    (out / "recipe-stdout.txt").write_text(result.stdout or "")
                    (out / "recipe-stderr.txt").write_text(result.stderr or "")
                    if result.exit_code:
                        raise RuntimeError("OriginalReferenceRecipeFailed")
                else:
                    dest = recipe["destination"]
                    sandbox.command(
                        sb,
                        "mkdir -p " + shlex.quote(str(Path(dest).parent)),
                        user="root",
                        timeout=30,
                    )
                    sb.files.write(
                        dest, source.read_bytes(), user="root", request_timeout=240
                    )
                    sandbox.command(
                        sb, "chmod 644 " + shlex.quote(dest), user="root", timeout=30
                    )
            legal = observe(sb, Path(spec["task_path"]), out / "legal")
        finally:
            sb.kill()
        positive = legal["exit_code"] == 0 and legal["reward"] == 1
        # Explicitly retain absence of a reward. This is control rejection,
        # never a fabricated normal model score of zero.
        negative = initial["reward"] == 0 or (
            initial["reward"] is None and initial["exit_code"] == 1 and positive
        )
        record = {
            "passed": positive and negative,
            "initial": initial,
            "legal": legal,
            "negative_channel": "reward"
            if initial["reward"] is not None
            else "rejected_without_reward",
            "original_spec_path": str(spec_path),
            "original_spec_sha256": sha(spec_path),
            "adapter_identity": spec["preflight_adapter_identity"],
            "source_original_outcome": spec["source"].get("original_outcome"),
            "elapsed_sec": time.time() - started,
            "new_model_requests": 0,
            "original_grader_unchanged": not bool(spec.get("verifier_revision")),
            "verifier_revision": spec.get("verifier_revision"),
        }
        dump(out / "receipt.json", record)
        dump(
            out / "status.json",
            {"phase": "passed" if record["passed"] else "semantic_or_control_hold"},
        )
    except Exception as e:
        dump(
            out / "status.json",
            {
                "phase": "hold",
                "error_type": type(e).__name__,
                "message": str(e)[:400],
                "new_model_requests": 0,
            },
        )
        import traceback

        (out / "traceback.txt").write_text(traceback.format_exc())


def main():
    p = argparse.ArgumentParser(__doc__)
    for key in ("census", "sandbox-credentials", "runtime-assets", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--prior-success-only", action="store_true")
    p.add_argument("--prior-zero-only", action="store_true")
    a = p.parse_args()
    a.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    rows = json.loads(a.census.read_text())["rows"]
    if a.prior_success_only:
        rows = [x for x in rows if x["source"].get("original_outcome") == 1]
    if a.prior_zero_only:
        rows = [x for x in rows if x["source"].get("original_outcome") == 0]
    dump(
        a.output / "selection.json",
        {"rows": rows, "source_census_sha256": sha(a.census), "new_model_requests": 0},
    )
    # These workers only restore/grade original captures, never call a model.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_one, item, a) for item in rows]
        for f in as_completed(futures):
            f.result()
            states = {
                x.parent.name: json.loads(x.read_text())
                for x in a.output.glob("units/*/status.json")
            }
            dump(
                a.output / "progress.json",
                {"selected": len(rows), "states": states, "new_model_requests": 0},
            )
    dump(a.output / "finished.json", {"at": time.time(), "new_model_requests": 0})


if __name__ == "__main__":
    main()
