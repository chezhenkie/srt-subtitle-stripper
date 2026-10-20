#!/usr/bin/env python3
"""Regression run for the srtstripper binary.

Runs the binary over a fixture x mode matrix in temporary sandboxes and
compares exit code, stdout, stderr and every produced file against the
checked-in expected results in tools/golden.json.

    python3 srtstripper/tools/golden_diff.py            # verify
    python3 srtstripper/tools/golden_diff.py --update   # regenerate expectations
    python3 srtstripper/tools/golden_diff.py --keep     # keep sandboxes

Expectations store only deviations from the pristine fixture set: any file not
listed under "files" must be an untouched fixture file. Message streams are
compared with CRLF and path-separator normalization so the expectation file is
valid on every platform; produced files are compared byte-exact.

Run from the repository root; expects srtstripper/target/release/srtstripper
unless --rust-bin is given.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
GOLDEN = HERE / "golden.json"

FIXTURES = {
    "basic.srt": (
        b"1\r\n"
        b"00:00:01,000 --> 00:00:03,500\r\n"
        b"Hello world.\r\n"
        b"\r\n"
        b"2\r\n"
        b"00:00:04,000 --> 00:00:06,000\r\n"
        b"Second cue line one\r\n"
        b"second cue line two\r\n"
        b"\r\n"
        b"\r\n"
        b"3\r\n"
        b"00:00:07,000 --> 00:00:09,000\r\n"
        b"1234\r\n"
        b"OK.\r\n"
    ),
    "lf.srt": (
        b"1\n00:00:01,000 --> 00:00:03,500\nHello world.\n\n"
        b"2\n00:00:04,000 --> 00:00:06,000\nSecond line\n\n"
    ),
    "doubling-blocks.srt": (
        b"1\n00:00:01,000 --> 00:00:02,000\nalpha beta\ngamma delta\n\n"
        b"2\n00:00:03,000 --> 00:00:04,000\nalpha beta\ngamma delta\n\n"
        b"3\n00:00:05,000 --> 00:00:06,000\nepsilon\n"
    ),
    "mixed-eol.srt": (
        b"alpha\r\nbeta\ngamma\r\n\r\ndelta\n"
    ),
    "bom.srt": (
        "\ufeff\u00c9t\u00e9 and \u4e2d\u6587\n\n"
        "\u0661\u0662:\u0663\u0664:\u0665\u0666,\u0667\u0668\u0669 --> x\n"
        "\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645\n\n"
        "\u00b2 line\n"
    ).encode("utf-8"),
    "cp1252.srt": b"caf\xe9 quote\x92s here\nsecond line\n\nthird\n",
    "undefined.srt": b"ok line\nbad:\x81 byte\n\xf0\x9f tail\nplain\n",
    "blank-runs.txt": (
        b"\n\n\ntext one\n12345\nline two\n\n\n\ntext three\n\n\n"
    ),
    "no-letters.txt": b"123 456\n---\n\t\n",
    "empty.txt": b"",
    "newline-only.txt": b"\n",
    "letters.txt": (
        "\u00b2\n\u2163\n\u0663\n\u2318\n\u4e2d\u6587\n\u00e9\n\uff3f\nline mix \u00bd\n"
    ).encode("utf-8"),
    "timecode-madness.srt": (
        "x01:02:03,456 --> y\n"
        "999:59:59,999 --> z\n"
        "\u0661\u0662:\u0663\u0664:\u0665\u0666,\u0667\u0668\u0669 --> w\n"
        "01:02:03.456\t\t--> 01:02:04\n"
        "00:00:00,000-->00:00:01,000\n"
        "first text\n"
        "12:34:56,789 --> 12:34:57,000\n"
        "second text\n"
        "strange: 0:0:00,000 --> nope\n"
        "07:08:09,012 --> end\n"
        "\n"
        "outside text\n"
    ).encode("utf-8"),
    "doubling.srt": (
        b"1\n00:00:00,400 --> 00:00:03,190\n \nfirst line here\n\n"
        b"2\n00:00:03,190 --> 00:00:03,200\nfirst line here\n \n\n"
        b"3\n00:00:03,200 --> 00:00:05,110\nfirst line here\nsecond line here\n\n"
        b"4\n00:00:05,110 --> 00:00:05,120\nsecond line here\n \n\n"
        b"5\n00:00:05,120 --> 00:00:07,000\nsecond line here\nthird line here\n\n"
        b"6\n00:00:07,000 --> 00:00:09,000\nno\nno\nno\n\n"
        b"7\n00:00:09,000 --> 00:00:11,000\nlater repeat\n\n"
        b"8\n00:00:11,000 --> 00:00:13,000\nlater repeat\n\n"
        b"9\n00:00:13,000 --> 00:00:15,000\nthird line here\n"
    ),
    ".hidden": b"alpha\n",
    "archive.tar.gz": b"beta\n",
    "foo.": b"gamma\n",
    "nodot": b"delta\n",
    "t\u00ebst.txt": "epsilon \u03b6\n".encode("utf-8"),
    "sub/inner.srt": b"1\n00:00:01,000 --> 00:00:02,000\ninner text\n",
}

MODES = {
    "default": [],
    "numbered": ["--numbered"],
    "timecode": ["--timecode"],
}

EXTRA_CASES = [
    ("out-custom", ["--out", "custom/deep/out.txt", "basic.srt"]),
    ("out-deep-numbered", ["--numbered", "--out", "deep/a/b/c.txt", "blank-runs.txt"]),
    ("out-dash", ["--out", "-", "basic.srt"]),
    ("out-empty", ["--out=", "basic.srt"]),
    ("out-dir", ["--out", "sub", "basic.srt"]),
    ("subdir-input", ["sub/inner.srt"]),
    ("subdir-input-tc", ["--timecode", "sub/inner.srt"]),
    ("dir-as-input", ["sub"]),
    ("dash-input", ["-"]),
    ("ddash-positional", ["--", "--numbered"]),
    ("unicode-name", ["t\u00ebst.txt", "--numbered"]),
    ("missing", ["nope.srt"]),
    ("unknown-short", ["-x", "basic.srt"]),
    ("unknown-long", ["--bogus", "basic.srt"]),
    ("unknown-only", ["--bogus"]),
    ("out-missing-val", ["--out"]),
    ("out-opt-like-val", ["--out", "--numbered"]),
    ("extra-positional", ["basic.srt", "extra.txt"]),
    ("mutex", ["--numbered", "--timecode", "basic.srt"]),
    ("flag-with-value", ["--timecode=x", "basic.srt"]),
    ("help", ["-h"]),
    ("help-prefix", ["--hel"]),
    ("no-args", []),
    # multiple inputs (drag-and-drop onto the exe)
    ("multi-input", ["basic.srt", "lf.srt"]),
    ("multi-input-missing", ["basic.srt", "nope.srt"]),
    ("multi-input-duplicate", ["basic.srt", "basic.srt"]),
    ("multi-out-error", ["--out", "x.txt", "basic.srt", "lf.srt"]),
    # srtstripper.json next to the exe
    ("config-timecode", ["basic.srt"], '{"mode": "timecode"}'),
    ("config-numbered", ["basic.srt"], '{"mode": "numbered"}'),
    ("config-text-explicit", ["basic.srt"], '{"mode": "text"}'),
    ("config-empty", ["basic.srt"], "{}"),
    ("config-unknown-key", ["basic.srt"], '{"mode": "text", "future-option": true}'),
    ("config-bad-mode", ["basic.srt"], '{"mode": "bogus"}'),
    ("config-bad-json", ["basic.srt"], '{"mode": '),
    ("config-mode-not-string", ["basic.srt"], '{"mode": 5}'),
    ("config-cli-override", ["--numbered", "basic.srt"], '{"mode": "timecode"}'),
    ("config-cli-override-mutex", ["--timecode", "basic.srt"], '{"mode": "numbered"}'),
]

# Failure messages of these cases carry OS-specific filesystem error text
# ("is a directory" vs "access denied"); only the exit code is compared.
RC_ONLY = {"out-empty", "out-dir"}


def msgkey(b: bytes) -> str:
    """Comparison key for stdout/stderr: UTF-8 with cp1252 fallback, CRLF
    normalized, path separators normalized -> portable expectation file."""
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        s = b.decode("cp1252", "replace")
    s = s.replace("\r\n", "\n")
    if os.name == "nt":
        s = s.replace("\\", "/")
    return s


def canon(rel: str) -> str:
    """Filesystem-canonical fixture key. Windows drops trailing dots and
    spaces from every path component, so the fixture "foo." lands as "foo"."""
    if os.name != "nt":
        return rel
    return "/".join(part.rstrip(". ") for part in rel.split("/"))


def populate(sandbox: Path) -> None:
    for name, data in FIXTURES.items():
        p = sandbox / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def deltas(root: Path) -> dict:
    """Deviations from the pristine fixture set: added/changed files map to
    their text, removed fixture files map to None."""
    by_canon = {canon(rel): data for rel, data in FIXTURES.items()}
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        cur = p.read_bytes()
        if by_canon.get(canon(rel)) != cur:
            out[rel] = cur.decode("utf-8")
    for rel in FIXTURES:
        if not (root / rel).is_file() and not (root / canon(rel)).is_file():
            out[rel] = None
    return out


def excerpt(s: str, limit: int = 300) -> str:
    return s if len(s) <= limit else s[:limit] + "..."


def cases():
    """(name, argv, config) triples; config is the raw srtstripper.json content
    written next to the binary before the run and removed after."""
    out = []
    for name, mode_args in MODES.items():
        for fname in FIXTURES:
            out.append((f"{fname}:{name}", mode_args + [fname], None))
    for case in EXTRA_CASES:
        out.append((case[0], case[1], case[2] if len(case) == 3 else None))
    return out


def run_one(cmd, argv, config):
    sandbox = Path(tempfile.mkdtemp(prefix="golden-", dir=SCRATCH))
    populate(sandbox)
    cfg_path = None
    if config is not None:
        cfg_path = Path(cmd[0]).resolve().parent / "srtstripper.json"
        cfg_path.write_text(config, encoding="utf-8", newline="\n")
    try:
        proc = subprocess.run(cmd + argv, cwd=sandbox, capture_output=True, timeout=60)
        result = {
            "rc": proc.returncode,
            "stdout": msgkey(proc.stdout),
            "stderr": msgkey(proc.stderr),
            "files": deltas(sandbox),
        }
        if config is not None:
            # the config error message carries the binary's absolute path;
            # normalize it so the expectation file is portable
            cfg_norm = str(cfg_path).replace("\\", "/") if os.name == "nt" else str(cfg_path)
            for key in ("stdout", "stderr"):
                result[key] = result[key].replace(cfg_norm, "srtstripper.json")
    finally:
        if cfg_path is not None and cfg_path.exists():
            cfg_path.unlink()
        if not KEEP:
            shutil.rmtree(sandbox, ignore_errors=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--rust-bin",
        default=str(REPO / "srtstripper" / "target" / "release" / "srtstripper"),
    )
    ap.add_argument("--update", action="store_true", help="rewrite golden.json from a run")
    ap.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    args = ap.parse_args()
    global KEEP, SCRATCH
    KEEP = args.keep
    SCRATCH = REPO / "_scratch"
    SCRATCH.mkdir(exist_ok=True)

    bin_path = Path(args.rust_bin)
    if not bin_path.is_file():
        print(f"FAIL: binary not found: {args.rust_bin} (cargo build --release)")
        return 1
    cmd = [str(bin_path.resolve())]
    all_cases = cases()

    if args.update:
        expected = {}
        for name, argv, config in all_cases:
            r = run_one(cmd, argv, config)
            expected[name] = {"rc": r["rc"]} if name in RC_ONLY else r
        tmp = GOLDEN.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(expected, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(GOLDEN)
        print(f"golden: wrote {len(expected)} cases -> {GOLDEN}")
        return 0

    if not GOLDEN.is_file():
        print(f"FAIL: expectations not found: {GOLDEN} (run with --update)")
        return 1
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    missing = [name for name, _, _ in all_cases if name not in expected]
    if missing:
        print(f"FAIL: {len(missing)} cases lack expectations, first: {missing[:5]}")
        print("run with --update to regenerate")
        return 1

    failures = 0
    for name, argv, config in all_cases:
        r = run_one(cmd, argv, config)
        exp = expected[name]
        problems = []
        if r["rc"] != exp.get("rc"):
            problems.append(f"rc expected={exp.get('rc')} actual={r['rc']}")
        if name not in RC_ONLY:
            if r["stdout"] != exp["stdout"]:
                problems.append(
                    f"stdout expected={excerpt(exp['stdout'])!r} actual={excerpt(r['stdout'])!r}"
                )
            if r["stderr"] != exp["stderr"]:
                problems.append(
                    f"stderr expected={excerpt(exp['stderr'])!r} actual={excerpt(r['stderr'])!r}"
                )
            if r["files"] != exp["files"]:
                exp_only = {
                    k: excerpt(repr(v), 200)
                    for k, v in exp["files"].items()
                    if r["files"].get(k) != v
                }
                act_only = {
                    k: excerpt(repr(v), 200)
                    for k, v in r["files"].items()
                    if exp["files"].get(k) != v
                }
                problems.append(f"files expected-only/diff={exp_only} actual-only/diff={act_only}")
        if problems:
            print(f"FAIL {name}: " + " | ".join(problems))
            failures += 1
        else:
            print(f"PASS {name}")

    total = len(all_cases)
    print(f"golden: {total - failures}/{total} cases matched")
    if failures and not KEEP:
        print("NOTE: sandboxes were removed; rerun with --keep to inspect")
    return 1 if failures else 0


if __name__ == "__main__":
    KEEP = False
    SCRATCH = None
    sys.exit(main())
