#!/usr/bin/env python3
"""Strip non-alphabetic lines from SRT/text files, with optional timecodes.

Second version of strip_nonalpha.py. Options:

  default           keep every line with at least one letter, drop index and
                    timestamp lines, keep blank lines for separation.
  --keep-timecodes  SRT-aware: one line per cue, "[HH:MM:SS] <merged text>",
                    index and timestamp lines consumed, cue text merged into a
                    single line. Text outside cues is kept as its own paragraph.
  --numbered        prefix every kept text line with a 5-digit counter
                    (00001, 00002, ...); blank separator lines stay unnumbered.
  --numbered-only   SRT look without timecodes: each text block gets its own
                    number line ("00001" above the text), blank lines kept.

Blank-line guarantee (all modes): paragraphs of text are always separated by
exactly one blank line. If dropping scaffolding lines would leave two text
paragraphs adjacent, a blank line is inserted. Runs of blank lines collapse to
one. Trailing blank lines are trimmed.

Encoding: UTF-8 read (BOM-safe) or cp1252 fallback, UTF-8 written. Original
line endings preserved.

Usage:
  python strip_srt.py "file.srt" [--keep-timecodes] [--numbered | --numbered-only] [--out "result.txt"]
  Default outputs: "<stem> - alpha.txt" / "<stem> - timecodes.txt" / "<stem> - numbered.txt",
  plus " numbered" in the suffix when --numbered is set on top of another mode.
"""
import argparse
import re
import sys
from pathlib import Path

LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
TIMECODE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.]\d{3}\s*-->")


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", "replace")


def is_blank(line: str) -> bool:
    return line == "" or line.isspace()


def has_letter(line: str) -> bool:
    return LETTER.search(line) is not None


def strip_default(lines) -> list:
    out = []
    last = None
    dropped = False
    for line in lines:
        if is_blank(line):
            if last != "blank":
                out.append("")
                last = "blank"
            dropped = False
        elif has_letter(line):
            if last == "text" and dropped:
                out.append("")
            out.append(line)
            last = "text"
            dropped = False
        else:
            dropped = True
    return out


def strip_timecodes(lines) -> list:
    paras = []
    cue_buf, plain_buf = [], []
    stamp = None

    def flush_cue():
        if cue_buf:
            paras.append(f"[{stamp}] " + " ".join(cue_buf))
            cue_buf.clear()

    def flush_plain():
        if plain_buf:
            paras.append(" ".join(plain_buf))
            plain_buf.clear()

    for line in lines:
        m = TIMECODE.search(line)
        if m:
            flush_plain()
            flush_cue()
            stamp = f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3)}"
        elif is_blank(line):
            flush_plain()
            flush_cue()
            stamp = None
        elif has_letter(line):
            if stamp is None:
                plain_buf.append(line.strip())
            else:
                cue_buf.append(line.strip())
    flush_plain()
    flush_cue()
    return paras


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Strip lines without letters; keep blank separators; optional SRT timecodes.")
    ap.add_argument("input", type=Path)
    ap.add_argument("--keep-timecodes", action="store_true",
                    help="SRT mode: one '[HH:MM:SS] text' paragraph per cue, cue text merged")
    num = ap.add_mutually_exclusive_group()
    num.add_argument("--numbered", action="store_true",
                     help="prefix each kept text line with a 5-digit counter (00001, 00002, ...)")
    num.add_argument("--numbered-only", action="store_true",
                     help="number on its own line per text block (SRT look, no timecodes), blank lines kept")
    ap.add_argument("--out", type=Path, help="output file (default: name derived from input)")
    args = ap.parse_args()

    if args.numbered_only and args.keep_timecodes:
        ap.error("--numbered-only writes number lines and no timecodes; drop --keep-timecodes")

    if not args.input.is_file():
        sys.stderr.write(f"FAIL: input not found: {args.input}\n")
        return 2

    text = read_text(args.input)
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()

    if args.keep_timecodes:
        paras = strip_timecodes(lines)
        suffix = " - timecodes"
        mode = "keep-timecodes"
    else:
        paras = strip_default(lines)
        suffix = " - alpha"
        mode = "default"
    if args.numbered:
        suffix += " numbered"
        mode += "+numbered"

    if args.numbered_only:
        blocks = []
        cur = []
        for line in paras:
            if line == "":
                if cur:
                    blocks.append(cur)
                    cur = []
            else:
                cur.append(line)
        if cur:
            blocks.append(cur)
        paras = []
        for i, block in enumerate(blocks, 1):
            if paras:
                paras.append("")
            paras.append(f"{i:05d}")
            paras.extend(block)
        suffix = " - numbered"
        mode = "numbered-only"
    suffix += ".txt"

    while paras and paras[-1] == "":
        paras.pop()

    if args.numbered:
        n = 0
        for i, line in enumerate(paras):
            if line != "":
                n += 1
                paras[i] = f"{n:05d} {line}"

    out = args.out or args.input.with_name(args.input.stem + suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    sep = (eol + eol) if args.keep_timecodes else eol
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(sep.join(paras) + eol if paras else "")

    print(f"PASS: mode={mode}, wrote {len(paras)} lines from {len(lines)} input lines -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
