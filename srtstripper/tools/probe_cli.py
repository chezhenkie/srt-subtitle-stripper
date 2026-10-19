#!/usr/bin/env python3
"""Probe srtstripper CLI edge behavior.

Runs the binary with edge-case argv in a temporary sandbox and prints the
exit code plus stdout/stderr for each case. Evidence tool for the CLI
surface: option prefix matching, ambiguity errors, --out handling, mode
mutual exclusion, repeat collapsing.

    python3 srtstripper/tools/probe_cli.py [--bin PATH]

Default binary: srtstripper/target/release/srtstripper.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

BASIC = (
    b"1\n00:00:01,000 --> 00:00:03,500\nHello world.\n\n"
    b"2\n00:00:04,000 --> 00:00:06,000\nSecond line\n"
)
DOUBLING = (
    b"1\n00:00:00,400 --> 00:00:03,190\n \nfirst line\n\n"
    b"2\n00:00:03,190 --> 00:00:03,200\nfirst line\n \n\n"
    b"3\n00:00:03,200 --> 00:00:05,110\nfirst line\nsecond line\n"
)

CASES = [
    ("dedupe-default", ["doubling.txt"]),
    ("dedupe-num-only", ["--numbered-only", "doubling.txt"]),
    ("keep-timecodes", ["--keep-timecodes", "doubling.txt"]),
    ("missing", ["nope.srt"]),
    ("no-args", []),
    ("unknown-short", ["-x", "basic.srt"]),
    ("unknown-long", ["--bogus", "basic.srt"]),
    ("unknown-only", ["--bogus"]),
    ("ambiguous", ["--num", "basic.srt"]),
    ("prefix-ok", ["--keep", "basic.srt"]),
    ("out-missing-val", ["--out"]),
    ("out-opt-like-val", ["--out", "--numbered"]),
    ("out-dash", ["--out", "-", "basic.srt"]),
    ("out-empty", ["--out=", "basic.srt"]),
    ("extra-positional", ["basic.srt", "extra.txt"]),
    ("mutex", ["--numbered", "--numbered-only", "basic.srt"]),
    ("keep+numonly", ["--numbered-only", "--keep-timecodes", "basic.srt"]),
    ("flag-with-value", ["--numbered=x", "basic.srt"]),
    ("help", ["-h"]),
    ("help-prefix", ["--hel"]),
    ("ddash-positional", ["--", "--numbered"]),
    ("multi-input", ["basic.srt", "doubling.txt"]),
    ("multi-input-missing", ["basic.srt", "nope.srt"]),
    ("multi-out-error", ["--out", "x.txt", "basic.srt", "doubling.txt"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--bin",
        default=str(REPO / "srtstripper" / "target" / "release" / "srtstripper"),
    )
    args = ap.parse_args()

    bin_path = Path(args.bin)
    if not bin_path.is_file() and bin_path.with_suffix(".exe").is_file():
        bin_path = bin_path.with_suffix(".exe")
    if not bin_path.is_file():
        print(f"FAIL: binary not found: {args.bin}")
        return 1

    sandbox = Path(tempfile.mkdtemp(prefix="probe-", dir=REPO / "_scratch"))
    (sandbox / "basic.srt").write_bytes(BASIC)
    (sandbox / "doubling.txt").write_bytes(DOUBLING)

    for name, argv in CASES:
        p = subprocess.run(
            [str(bin_path.resolve()), *argv],
            cwd=sandbox,
            capture_output=True,
            timeout=60,
        )
        print(f"[{name}] argv={argv!r} rc={p.returncode}", flush=True)
        if p.stdout:
            sys.stdout.write(p.stdout.decode("utf-8", "replace"))
            sys.stdout.flush()
        if p.stderr:
            sys.stderr.write(p.stderr.decode("utf-8", "replace"))
            sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
