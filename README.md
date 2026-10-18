# srt-subtitle-stripper

Strips non-alphabetic lines from SRT/text subtitle files. Standalone Rust binary named `srtstripper`, zero runtime dependencies. Byte-for-byte parity with the original Python script, kept for reference in `deprecated-py-src/`.

## Usage

    srtstripper "file.srt" [--keep-timecodes] [--numbered | --numbered-only] [--out "result.txt"]

- default: keep every line with at least one letter, drop index and timestamp lines, keep blank lines for separation.
- `--keep-timecodes`: SRT-aware; one paragraph per cue, `"[HH:MM:SS] merged text"`.
- `--numbered`: prefix every kept text line with a 5-digit counter (`00001`, `00002`, ...); blank separator lines stay unnumbered.
- `--numbered-only`: SRT look without timecodes; a number line (`00001`) above each text block, blank lines kept. Cannot be combined with `--keep-timecodes`.

Default outputs: `"<stem> - alpha.txt"`, `"<stem> - timecodes.txt"`, `"<stem> - numbered.txt"`; `--numbered` stacked on another mode appends `" numbered"` to the suffix. Existing `--out` parent directories are created.

Exit codes: 0 success, 2 usage error or input not found, 1 I/O error.

Blank-line guarantee (all modes): exactly one blank line between paragraphs; runs of blank lines collapse to one; trailing blank lines are trimmed.

Encoding: UTF-8 (BOM-safe), cp1252 fallback, then UTF-8 with CPython-exact replacement handling. Output is UTF-8; CRLF vs LF is detected from the input and preserved.

## Windows behavior

The exe is built as a GUI-subsystem binary, so no console window ever appears when another app launches it. Started from a console it attaches to the parent console to print PASS/FAIL; redirected stdout/stderr (pipes, files) are always honored. Right click the exe, Properties, Details shows the filled-in version metadata.

Note: cmd and PowerShell only wait for console-subsystem programs. Callers that need completion or exit codes should wait on the process - Python's subprocess API, `cmd /c "srtstripper ... > out.txt"` and `Start-Process -Wait -RedirectStandardOutput` all behave correctly; a bare invocation in an interactive Windows PowerShell 5.1 prompt returns immediately, as with any GUI-subsystem tool.

## Install

Prebuilt binaries are attached to every release; the same commands are in the release text. Replace `latest` with a tag such as `v1.0.0` to pin a version.

### Linux (x86_64)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-linux-x86_64
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

Without root, install into a user directory instead: `install -m 0755 srtstripper ~/.local/bin/srtstripper` (when `~/.local/bin` is on `PATH`).

### Alpine Linux / musl (x86_64)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-linux-x86_64-musl
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

Statically linked against musl, so it runs on any Linux distribution, glibc or not (Alpine, Void, containers, initramfs).

### macOS (Apple Silicon)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-macos-arm64
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

The binary is not notarized; files fetched with curl carry no quarantine flag and just run. If it was downloaded with a browser instead, clear the flag with `xattr -d com.apple.quarantine srtstripper` (or open it once via right click, Open). There is no Intel macOS build yet.

### Windows (PowerShell or cmd)

    curl.exe -L -o srtstripper.exe https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-windows-x86_64.exe

## Build from source

    cd srtstripper
    cargo build --release --locked

## CI and releases

GitHub Actions runs fmt, clippy (`-D warnings`), build, unit tests and an end-to-end smoke on Linux, Windows, macOS and a statically linked musl build for Alpine and other non-glibc systems, and uploads the binaries as artifacts. Pushing a tag `v*` publishes a GitHub release with the binaries attached.

## Parity testing

    python3 srtstripper/tools/golden_diff.py

runs the Python original and the Rust binary over a fixture set times all modes and compares exit codes, stdout, stderr and every output file byte-for-byte.

Unicode tables for `\w`, `\d`, `\s`, `isspace`, `splitlines` and cp1252 are generated from CPython 3.14 (Unicode 16.0.0) by `srtstripper/tools/gen_tables.py` into `srtstripper/src/tables.rs`, because Python's and Rust's built-in sets are not identical (e.g. U+001C..U+001F are Python whitespace but not Rust whitespace). The lossy UTF-8 decoder replicates CPython's exact error grouping.

## Project docs

- Requirements and design constraints: `REQUIREMENTS.md`.
- Release history: `CHANGELOG.md`.
- Porting pitfalls honored by this rewrite: `python-to-rust-refactor-pitfalls.md`.
- License: MIT, see `LICENSE`.
