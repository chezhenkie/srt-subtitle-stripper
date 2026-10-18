#!/usr/bin/env python3
"""Windows acceptance check: GUI-subsystem exe runs with no console/handles.

Simulates the "called by another app" case: DETACHED_PROCESS (no console), all
std handles DEVNULL. The process must exit 0 without hanging and write its
output file. Windows only.

Usage:
    python srtstripper/tools/check_noconsole.py path\\to\\srtstripper.exe [--keep]
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", help="path to the Windows srtstripper exe")
    ap.add_argument("--keep", action="store_true", help="keep the scratch dir")
    args = ap.parse_args()
    if sys.platform != "win32":
        print("FAIL: this check is Windows only")
        return 1
    scratch = REPO / "_scratch"
    scratch.mkdir(exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix="noconsole-", dir=scratch))
    (d / "sample.srt").write_bytes(
        b"1\n00:00:01,000 --> 00:00:02,000\nHello there.\n"
    )
    DETACHED_PROCESS = 0x00000008
    p = subprocess.Popen(
        [str(Path(args.exe).resolve()), "sample.srt"],
        cwd=d,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS,
    )
    rc = p.wait(timeout=30)
    out = (d / "sample - alpha.txt").read_bytes()
    print(f"rc={rc} output={out!r}")
    ok = rc == 0 and b"Hello there." in out
    if not args.keep:
        shutil.rmtree(d, ignore_errors=True)
    print("PASS spawn-without-console" if ok else "FAIL spawn-without-console")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
