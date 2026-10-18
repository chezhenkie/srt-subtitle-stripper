# Changelog

All notable changes to this project are documented in this file. The format follows Keep a Changelog and the project uses semantic versioning.

## [1.0.1] - 2026-10-18

### Added

- Statically linked musl build `srtstripper-linux-x86_64-musl`: runs on any Linux distribution without glibc, including Alpine. Built, tested and smoked in CI alongside the existing targets; install commands in the README and the release text.

### Fixed

- `tools/golden_diff.py` resolves a user-supplied `--rust-bin` or `--py-script` path against the caller's directory, so relative paths also work on POSIX (cases run in sandbox working directories).

## [1.0.0] - 2026-10-18

First standalone release of srtstripper, a byte-for-byte Rust port of the original Python script.

### Added

- `srtstripper` CLI with the full Python feature set: default mode, `--keep-timecodes`, `--numbered`, `--numbered-only` and `--out`, including the exact output naming scheme and exit codes.
- Byte-for-byte output parity with `deprecated-py-src/strip_srt.py`, validated by a golden differential suite that compares exit code, stdout, stderr and every produced file (sha256) across five modes times a fixture set, on Linux and on the shipped Windows binary.
- Oracle-generated Unicode tables (CPython 3.14, Unicode 16.0.0) for the letter, digit, whitespace and cp1252 sets, plus a CPython-exact lossy UTF-8 decoder.
- Windows GUI-subsystem build: no console window when another app launches it, parent-console attach for interactive use, and filled-in Properties/Details version metadata.
- GitHub Actions pipeline building `srtstripper-linux-x86_64`, `srtstripper-macos-arm64` and `srtstripper-windows-x86_64.exe`, running fmt, clippy, unit tests and an end-to-end smoke on every push, and publishing tagged releases.
- Install instructions for Linux, macOS and Windows in the README, using curl against the release assets.

### Notes

- Known presentation deviations are documented in the README: Windows stdout encoding and line endings, and PowerShell 5.1 not waiting for GUI-subsystem processes.
