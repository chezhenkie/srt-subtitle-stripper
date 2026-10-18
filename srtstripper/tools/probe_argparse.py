#!/usr/bin/env python3
"""Probe argparse edge behaviors of the original strip_srt.py CLI, for the Rust port.

Runs the real script via subprocess with edge-case argv; prints exit code,
stdout/stderr first line. Evidence for matching parse behavior.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent.parent / "deprecated-py-src" / "strip_srt.py"

CASES = [
    ["--out", "--numbered"],
    ["--out"],
    ["--out", "-h"],
    ["--num", "x.srt"],
    ["--numbered=x", "x.srt"],
    ["--out=", "x.srt"],
    ["-x", "x.srt"],
    ["x.srt", "y.srt"],
    ["--keep", "x.srt"],
    ["--numbered-o", "x.srt"],
    ["--", "--numbered"],
    [],
    ["-h"],
    ["--bogus", "-h"],
    ["--bogus"],
    ["-hx"],
    ["-xh"],
    ["--hel"],
    ["--ke"],
    ["--keep-timecodes", "--numbered-only", "x.srt"],
    ["--numbered", "--numbered-only", "x.srt"],
    ["--out=out.txt"],
    ["--out", "-"],
    ["--out", "-x"],
    ["-"],
    ["--numbered", "--out"],
    ["--NUMBERED", "x.srt"],
    ["--numbered-only", "--keep-timecodes", "x.srt"],
]

for argv in CASES:
    p = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)
    out = (p.stdout or "").strip().splitlines()
    err = (p.stderr or "").strip().splitlines()
    first_err = err[-1] if err else ""
    first_out = out[0] if out else ""
    print(f"argv={argv!r} rc={p.returncode} out={first_out!r} err={first_err!r}")
