"""Hash-bound offline tmux layer for owned Debian12/compatible sandboxes.

No apt/pip/network fallback and no shared image changes. Artifacts live in an
external persistent root and retain distro copyright notices.
"""

import argparse
import json
from pathlib import Path
import shutil

from ..collect import sha
from .. import sandbox


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    copies = {
        "/usr/bin/tmux": "bin/tmux.real",
        "/lib/x86_64-linux-gnu/libutempter.so.0": "lib/libutempter.so.0",
        "/lib/x86_64-linux-gnu/libtinfo.so.6": "lib/libtinfo.so.6",
        "/lib/x86_64-linux-gnu/libevent_core-2.1.so.7": "lib/libevent_core-2.1.so.7",
        "/lib/terminfo/x/xterm-256color": "terminfo/x/xterm-256color",
    }
    for src, dest in copies.items():
        p = output / dest
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, p)
        p.chmod(0o755 if dest == "bin/tmux.real" else 0o644)
    for package in ["tmux", "libtinfo6", "libevent-core-2.1-7", "libutempter0"]:
        source = Path("/usr/share/doc") / package / "copyright"
        if source.exists():
            p = output / "licenses" / package
            p.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, p)
    (output / "tmux-wrapper").write_text(
        '#!/bin/sh\nexport LD_LIBRARY_PATH=/opt/terminus-runtime/lib\nexport TERMINFO=/opt/terminus-runtime/terminfo\nexec /opt/terminus-runtime/bin/tmux.real "$@"\n'
    )
    (output / "tmux-wrapper").chmod(0o755)
    manifest = {
        str(p.relative_to(output)): {"sha256": sha(p), "mode": p.stat().st_mode & 511}
        for p in output.rglob("*")
        if p.is_file()
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "offline-tmux-layer.v1",
                "compatibility": "x86_64 glibc >=2.35; target smoke required",
                "files": manifest,
            },
            indent=2,
        )
    )


def install(sb, root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    actual = {
        str(p.relative_to(root)): {"sha256": sha(p), "mode": p.stat().st_mode & 511}
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if actual != manifest["files"] or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("Offline runtime asset drift")
    sandbox.upload(sb, root, "/opt/terminus-runtime")
    checks = (
        "\n".join(
            x["sha256"] + "  /opt/terminus-runtime/" + name
            for name, x in manifest["files"].items()
        )
        + "\n"
    )
    sb.files.write("/opt/terminus-runtime/SHA256SUMS", checks, user="root")
    q = sandbox.command(
        sb,
        "sha256sum -c /opt/terminus-runtime/SHA256SUMS && install -m 755 /opt/terminus-runtime/tmux-wrapper /usr/local/bin/tmux && tmux -V && tmux -L owned-preflight new-session -d -s probe && tmux -L owned-preflight kill-server",
        user="root",
        timeout=30,
    )
    if q.exit_code:
        raise RuntimeError("OfflineTmuxSmokeFailed")
    return {
        "asset_manifest_sha256": sha(root / "manifest.json"),
        "smoke_returncode": q.exit_code,
        "offline": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)
