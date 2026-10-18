#!/usr/bin/env python3
"""Golden differential test: deprecated strip_srt.py vs the Rust srtstripper.

Runs both implementations on identical sandboxes for every case and compares:
  exit code, stdout, stderr, and every file the run produced (sha256).
Expected to run from the repository root, e.g. inside WSL:

    python3 srtstripper/tools/golden_diff.py

Requires the Rust binary at srtstripper/target/release/srtstripper
(cargo build --release first).
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

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
    "timecodes": ["--keep-timecodes"],
    "tc+num": ["--keep-timecodes", "--numbered"],
    "num-only": ["--numbered-only"],
}

# Cases where only the exit code is comparable (help/usage text and traceback
# style error output legitimately differ between Python and Rust).
RC_ONLY_CASES = [
    ("missing", ["nope.srt"]),
    ("unknown-short", ["-x", "basic.srt"]),
    ("unknown-long", ["--bogus", "basic.srt"]),
    ("unknown-only", ["--bogus"]),
    ("ambiguous", ["--num", "basic.srt"]),
    ("out-missing-val", ["--out"]),
    ("out-opt-like-val", ["--out", "--numbered"]),
    ("extra-positional", ["basic.srt", "extra.txt"]),
    ("mutex", ["--numbered", "--numbered-only", "basic.srt"]),
    ("keep+numonly", ["--numbered-only", "--keep-timecodes", "basic.srt"]),
    ("flag-with-value", ["--numbered=x", "basic.srt"]),
    ("help", ["-h"]),
    ("out-empty", ["--out=", "basic.srt"]),
    ("out-dir", ["--out", "sub", "basic.srt"]),
]

FULL_EXTRA_CASES = [
    ("out-custom", ["--out", "custom/deep/out.txt", "basic.srt"]),
    ("out-deep-numbered", ["--numbered", "--out", "deep/a/b/c.txt", "blank-runs.txt"]),
    ("out-dash", ["--out", "-", "basic.srt"]),
    ("subdir-input", ["sub/inner.srt"]),
    ("subdir-input-tc", ["--keep-timecodes", "sub/inner.srt"]),
    ("dir-as-input", ["sub"]),
    ("dash-input", ["-"]),
    ("ddash-positional", ["--", "--numbered"]),
    ("unicode-name", ["t\u00ebst.txt", "--numbered"]),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def msgkey(b: bytes) -> str:
    """Comparison key for stdout/stderr messages.

    On Linux/macOS this is a plain decode plus CRLF normalization. On Windows
    Python's piped stdout uses the ANSI codepage (e.g. cp1252) and prints
    Windows path separators; the Rust binary always writes UTF-8 with the
    caller's separators. The key unifies that presentation layer; exit codes
    and every output file stay byte-exact in all cases.
    """
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        s = b.decode("cp1252", "replace")
    s = s.replace("\r\n", "\n")
    if os.name == "nt":
        s = s.replace("\\", "/")
    return s


def tree(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = sha(p)
    return out


def populate(sandbox: Path) -> None:
    for name, data in FIXTURES.items():
        p = sandbox / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def run_one(cmd, argv, keep_dir):
    sandbox = Path(tempfile.mkdtemp(prefix="golden-", dir=keep_dir))
    populate(sandbox)
    proc = subprocess.run(cmd + argv, cwd=sandbox, capture_output=True, timeout=60)
    files = tree(sandbox)
    if not KEEP:
        shutil.rmtree(sandbox, ignore_errors=True)
    return proc.returncode, proc.stdout, proc.stderr, files


def excerpt(b: bytes, limit: int = 300) -> str:
    s = repr(b)
    return s if len(s) <= limit else s[:limit] + "..."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--py-script", default=str(REPO / "deprecated-py-src" / "strip_srt.py"))
    ap.add_argument("--rust-bin", default=str(REPO / "srtstripper" / "target" / "release" / "srtstripper"))
    ap.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    args = ap.parse_args()
    global KEEP
    KEEP = args.keep

    py_cmd = [args.python, args.py_script]
    rs_cmd = [args.rust_bin]
    if not Path(args.py_script).is_file():
        print(f"FAIL: python script not found: {args.py_script}")
        return 1
    if not Path(args.rust_bin).is_file():
        print(f"FAIL: rust binary not found: {args.rust_bin} (cargo build --release)")
        return 1

    print(
        f"oracle: python {sys.version.split()[0]} unicode {unicodedata.unidata_version}, "
        f"py={args.py_script}, rust={args.rust_bin}"
    )
    scratch = REPO / "_scratch"
    scratch.mkdir(exist_ok=True)

    cases = []
    for name, mode_args in MODES.items():
        for fname in FIXTURES:
            cases.append((f"{fname}:{name}", "full", mode_args + [fname]))
    for name, argv in FULL_EXTRA_CASES:
        cases.append((name, "full", argv))
    for name, argv in RC_ONLY_CASES:
        cases.append((name, "rc", argv))

    failures = 0
    for name, kind, argv in cases:
        try:
            py_rc, py_out, py_err, py_files = run_one(py_cmd, argv, scratch)
            rs_rc, rs_out, rs_err, rs_files = run_one(rs_cmd, argv, scratch)
        except subprocess.TimeoutExpired:
            print(f"FAIL {name}: timeout")
            failures += 1
            continue
        if py_rc != rs_rc:
            print(f"FAIL {name}: rc python={py_rc} rust={rs_rc}")
            failures += 1
            continue
        if kind == "rc":
            print(f"PASS {name}")
            continue
        problems = []
        if msgkey(py_out) != msgkey(rs_out):
            problems.append(f"stdout py={excerpt(py_out)} rust={excerpt(rs_out)}")
        if msgkey(py_err) != msgkey(rs_err):
            problems.append(f"stderr py={excerpt(py_err)} rust={excerpt(rs_err)}")
        if py_files != rs_files:
            only_py = {k: v for k, v in py_files.items() if rs_files.get(k) != v}
            only_rs = {k: v for k, v in rs_files.items() if py_files.get(k) != v}
            problems.append(f"files py-only/diff={only_py} rust-only/diff={only_rs}")
        if problems:
            print(f"FAIL {name}: " + " | ".join(problems))
            failures += 1
        else:
            print(f"PASS {name}")

    total = len(cases)
    print(f"golden: {total - failures}/{total} cases matched")
    if failures:
        print("NOTE: sandboxes were removed; rerun with --keep to inspect")
    return 1 if failures else 0


if __name__ == "__main__":
    KEEP = False
    sys.exit(main())
