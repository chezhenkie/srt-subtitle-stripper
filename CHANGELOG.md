# Changelog

All notable changes to this project are documented in this file. The format follows Keep a Changelog and the project uses semantic versioning.

## [1.6.5]

### Fixed

- A `srtstripper.json` with deeply nested JSON no longer aborts the process with a stack overflow; nesting is capped at 32 levels and reported as a config error (exit code 2).
- Input paths that are not valid UTF-8 are handled as raw OS paths instead of a lossy UTF-8 rewrite, so the input file is found and the output name keeps the original bytes.
- Windows installer: an unreadable user PATH is left unchanged instead of being overwritten with only the install directory.
- Windows installer: the uninstaller removes the PATH entry only when the setup added it, so a silent install with `/TASKS=` no longer removes an entry it never created.
- Windows installer: adding the PATH entry keeps an existing trailing separator, so install and uninstall round-trip the user PATH unchanged.

### Changed

- Help text, README and REQUIREMENTS state the config/flag interaction accurately: a mode flag enables its mode on top of the config, and conflicting modes are rejected.
- CI: workflow-level token permissions reduced to `contents: read`; only the release job has `contents: write`. Clippy runs with `--all-targets`, matching the local gate.
- README and REQUIREMENTS document the memory model: input and output are buffered whole, peak memory is roughly 4-5x the input size, and multi-gigabyte inputs are not streamed.

## [1.6.4]

### Fixed

- Windows file Properties: the numeric FILEVERSION/PRODUCTVERSION fields were stale at 1.4.1.0 since v1.4.1 (only the string fields were bumped on releases); now 1.6.4.0. CI and installer/build-installers.ps1 verify the numeric fields against Cargo.toml, which catches this class of drift.

### Changed

- Argument-level usage errors (missing input, unrecognized arguments, missing --out value, ignored flag argument, mode conflict, --out with multiple inputs) now print an examples block after the error line.

## [1.6.3]

### Changed

- `--timecode` writes the `[HH:MM:SS]` stamp on its own line above the text, one block per cue, matching the numbered block layout.
- A blank line directly after a cue timestamp no longer clears the stamp, so a cue whose text starts with a blank line keeps its timecode and the first block is stamped.
- Windows installer: the license agreement page is removed; `LICENSE` is still installed next to the exe.
- Windows installer: the desktop shortcut task is removed.

## [1.6.2]

### Fixed

- `--timecode` removes rolling-caption overlap instead of only dropping identical paragraphs. Each paragraph is trimmed at a word boundary against the text already emitted, so a cue writes only its new words with its own stamp. A fully repeated paragraph is dropped.

## [1.6.1]

### Fixed

- `--numbered` collapses repeated text blocks, not only repeated single lines. The comparison is on the merged block text, so a repeated multi-line cue is dropped whole.

## [1.6.0]

### Changed

- `--numbered-only` renamed to `--numbered`; `--keep-timecodes` renamed to `--timecode`. All modes collapse consecutive repeated text.

### Removed

- The old `--numbered` flag (5-digit counter prefix per kept text line) is removed. The `--numbered` name now refers to the SRT-look mode (number line per text block), formerly `--numbered-only`.

## [1.5.0]

### Added

- `--keep-timecodes` collapses consecutive repeated paragraphs to the first occurrence. The comparison is on the merged paragraph text only; the cue stamp is not part of it, and the kept paragraph keeps its own stamp.

### Removed

- The `--keep-timecodes` + `--numbered` combination is rejected with a usage error (`srtstripper: error: --keep-timecodes writes timecodes and no line numbers; drop --numbered`); the `keep-timecodes+numbered` mode no longer exists.

## [1.4.1]

### Added

- Windows installer creates a `srtstripper` shortcut in the Start Menu (so the app appears in All apps) and offers a desktop shortcut through a setup checkbox. Taskbar pinning stays unavailable because Windows does not allow installers to pin to the taskbar.

## [1.4.0]

### Added

- Dropper support: several input files may be given at once (Windows drag-and-drop onto the exe passes each dropped file as a bare path). Each input is processed in order with the same flags and prints its own PASS line; the exit code is the worst of the run. `--out` is rejected with more than one input.
- Optional `srtstripper.json` next to the exe selects the mode when no mode flag is passed. The file is a flat JSON object with a `mode` key (`text` default, `timecodes`, `numbered`, `numbered-only`); unknown keys are ignored, a missing file means text mode, and a malformed file or unknown mode is an error (exit code 2). Command line flags override the config.

### Changed

- Golden regression suite extended to 136 cases: multiple inputs and the config file.
- Help text and usage line document multiple inputs and the config file.

## [1.3.0]

### Added

- Windows installers `srtstripper-windows-x86_64-setup.exe` and `srtstripper-windows-aarch64-setup.exe`: per-user, no elevation, installs to `%LOCALAPPDATA%\Programs\srtstripper`, adds the folder to the user PATH, registers an uninstaller in Settings > Apps. Built in CI from the Windows release binaries with Inno Setup and attached to releases.
- `installer/` with the Inno Setup script and `build-installers.ps1`; CI job `windows-installers` feeds the release job, so `SHA256SUMS` covers the setup executables.
- README Windows install section documents the installer and the standalone exe.

## [1.2.0]

### Added

- `srtstripper-windows-aarch64.exe` native Windows ARM64 build, tested on a native ARM64 runner; GUI subsystem and version metadata match the x86_64 build.
- CI runs the golden suite on all seven targets and verifies version metadata on both Windows builds.

## [1.1.1]

### Added

- `srtstripper-linux-aarch64` and statically linked `srtstripper-linux-aarch64-musl` builds for ARM64 Linux, including Alpine; built, tested and smoked on native ARM64 runners.
- `SHA256SUMS` attached to every release; install docs show how to verify downloads.

### Changed

- CI runs the 120-case golden regression suite on all six targets, including both ARM64 builds.
- Release builds pinned to Ubuntu 24.04 (x86_64 and ARM64) so the glibc floor does not move with `ubuntu-latest`; workflow actions bumped to checkout v7, upload-artifact v7 and download-artifact v8.

### Fixed

- Windows exe `FileVersion` and `ProductVersion` strings report the crate version (`1.1.1.0`); CI compares the built exe metadata with `Cargo.toml`.

## [1.1.0]

### Changed

- Default mode and `--numbered-only` collapse consecutive repeated text lines (rolling-caption doublings) to the first occurrence; blank separators between repeats shrink to one. `--numbered` and `--keep-timecodes` are unaffected.
- Regression suite reworked: `tools/golden_diff.py` runs the binary over the fixture x mode matrix and compares exit codes, stdout, stderr and every produced file against checked-in expected results in `tools/golden.json`; `--update` regenerates them. Fixture names are canonicalized on Windows (trailing dots are dropped by the filesystem), so the suite runs on the Windows exe as well.
- CLI probe reworked: `tools/probe_cli.py` drives the binary with edge argv and prints rc/stdout/stderr for each case.

### Added

- `doubling.srt` fixture in the regression matrix: triple repeats, adjacent repeats, gap-cue filler lines and kept non-consecutive repeats across all five modes.

### Removed

- `tools/probe_argparse.py`, superseded by `tools/probe_cli.py`.

## [1.0.1]

### Added

- Statically linked musl build `srtstripper-linux-x86_64-musl`: runs on any Linux distribution without glibc, including Alpine. Built, tested and smoked in CI alongside the existing targets; install commands in the README and the release text.

### Fixed

- `tools/golden_diff.py` resolves a user-supplied `--rust-bin` or `--py-script` path against the caller's directory, so relative paths also work on POSIX (cases run in sandbox working directories).

## [1.0.0]

First release of srtstripper, a standalone Rust CLI that strips non-alphabetic lines from SRT/text subtitle files.

### Added

- CLI with four modes: default, `--keep-timecodes`, `--numbered`, `--numbered-only`, plus `--out`; output naming `"<stem> - alpha.txt"`, `"<stem> - timecodes.txt"`, `"<stem> - numbered.txt"` and exit codes 0 success, 2 usage error or input not found, 1 I/O error.
- Unicode property tables (letter, digit, whitespace, cp1252) and a lossy UTF-8 decoder with fully specified invalid-sequence grouping, generated by `srtstripper/tools/gen_tables.py`.
- Windows GUI-subsystem build: no console window when another app launches the exe, parent-console attach for interactive use, filled-in Properties/Details metadata.
- GitHub Actions pipeline building `srtstripper-linux-x86_64`, `srtstripper-macos-arm64` and `srtstripper-windows-x86_64.exe`, running fmt, clippy, unit tests and an end-to-end smoke on every push, and publishing tagged releases.
- Install instructions for Linux, macOS and Windows in the README, using curl against the release assets.

### Notes

- Known platform deviations are documented in the README: Windows stdout encoding and line endings, and PowerShell 5.1 not waiting for GUI-subsystem processes.
