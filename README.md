# srt-subtitle-stripper

### Strips timecodes lines and de-duplicates lines from SRT/text subtitle files. Standalone Rust binary, zero runtime dependencies.

## Repeat collapsing

Rolling-caption subtitles repeat each line in overlapping cues before advancing, so the same text appears two or three times in a row. Default and `--numbered` keep only the first occurrence of a run of identical text lines. A non-consecutive repeat is kept, so dialogue that genuinely repeats later survives.

- The comparison is exact text equality after decoding; the reference is the last kept line.
- Blank separators between repeats do not break the run: the run collapses and leaves one blank line.
- `--timecode` trims each paragraph against the text already emitted: the longest word-boundary overlap at the end of that text is removed, so a rolling cue writes only its new words. The `[HH:MM:SS]` stamp sits on its own line above the text, and a fully covered paragraph is dropped.
- The cue stamp is never part of the comparison.

Input:

    2
    00:00:03,190 --> 00:00:03,200
    The Earth is extremely old and so is the
 

    3
    00:00:03,200 --> 00:00:05,110
    The Earth is extremely old and so is the
    life that inhabits it with the oldest


Default output:

    The Earth is extremely old and so is the
    life that inhabits it with the oldest


Numbered Output:

    00001
    The Earth is extremely old and so is the

    00002
    life that inhabits it with the oldest

Timecode Output:

    

## Usage

    srtstripper "file.srt" ["file2.srt" ...] [--timecode] [--numbered] [--out "result.txt"]

Several input files may be given; each is processed in order with the same flags and gets its own PASS line. `--out` is only valid with a single input.

- default: keep every line with at least one letter, drop index and timestamp lines, keep blank lines for separation; consecutive repeated text lines collapse to the first occurrence.
- `--timecode`: SRT-aware; one block per cue: a `[HH:MM:SS]` line followed by the cue's new text. Each paragraph is trimmed of the words already shown, so only new text is written under the cue's own stamp; a fully repeated paragraph is dropped. Cannot be combined with `--numbered`.
- `--numbered`: SRT look without timecodes; a number line (`00001`) above each text block, blank lines kept; consecutive repeated text lines and repeated blocks collapse to the first occurrence. Cannot be combined with `--timecode`.

Default outputs: `"<stem> - alpha.txt"`, `"<stem> - timecodes.txt"`, `"<stem> - numbered.txt"`. Existing `--out` parent directories are created.

Exit codes: 0 success, 2 usage error, input not found or a bad config file, 1 I/O error.

Blank-line guarantee (all modes): exactly one blank line between paragraphs; runs of blank lines collapse to one; trailing blank lines are trimmed.

Repeat collapsing applies to all modes: a run of identical text lines, even separated by blank lines, is reduced to its first occurrence and the separators shrink to one. In `--timecode` only words not already shown are written, so overlapping cues never repeat text and the stamp is never part of the comparison.

Encoding: UTF-8 (BOM-safe), cp1252 fallback, then UTF-8 with permissive replacement decoding for invalid bytes. Output is UTF-8; CRLF vs LF is detected from the input and preserved.

## Drag and drop

Drop one or more SRT/text files onto the exe: each dropped file arrives as a bare path argument and is processed in order, writing its cleaned copy next to the source. No console window appears, since the exe is a GUI-subsystem binary; started from a console the per-file PASS lines are printed. A dropped folder is not scanned, so point the dropper at files.

## Configuration

An optional `srtstripper.json` file next to the exe sets the mode when no mode flag is passed, which is what a dropper run uses. The default with no file is the text mode.

    {"mode": "timecode"}

- `mode`: `text` (default), `timecode`, `numbered`.
- Unknown keys are ignored, so a config written for a newer version still loads in an older exe.
- A missing file means text mode; a malformed file, a non-string `mode` or an unknown mode value is an error (exit code 2).
- Flags on the command line win over the config.

## Windows behavior

The exe is built as a GUI-subsystem binary, so no console window ever appears when another app launches it. Started from a console it attaches to the parent console to print PASS/FAIL; redirected stdout/stderr (pipes, files) are always honored. Right click the exe, Properties, Details shows the filled-in version metadata.

Note: cmd and PowerShell only wait for console-subsystem programs. Callers that need completion or exit codes should wait on the process - subprocess APIs, `cmd /c "srtstripper ... > out.txt"` and `Start-Process -Wait -RedirectStandardOutput` all behave correctly; a bare invocation in an interactive Windows PowerShell 5.1 prompt returns immediately, as with any GUI-subsystem tool.

## Install

Prebuilt binaries are attached to every release; the same commands are in the release text. Replace `latest` with a tag such as `v1.2.0` to pin a version.

Each release ships `SHA256SUMS`. Verify a download with `sha256sum -c SHA256SUMS --ignore-missing`; on Windows compare `certutil -hashfile <file> SHA256` with the matching entry.

### Linux (x86_64)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-linux-x86_64
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

Without root, install into a user directory instead: `install -m 0755 srtstripper ~/.local/bin/srtstripper` (when `~/.local/bin` is on `PATH`).

### Linux (ARM64)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-linux-aarch64
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

### Alpine Linux / musl (x86_64)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-linux-x86_64-musl
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

Statically linked against musl, so it runs on any Linux distribution, glibc or not (Alpine, Void, containers, initramfs).

### Alpine Linux / musl (ARM64)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-linux-aarch64-musl
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

Statically linked against musl for ARM64 systems without glibc.

### macOS (Apple Silicon)

    curl -fsSL -o srtstripper https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-macos-arm64
    sudo install -m 0755 srtstripper /usr/local/bin/srtstripper
    srtstripper -h

The binary is not notarized; files fetched with curl carry no quarantine flag and just run. If it was downloaded with a browser instead, clear the flag with `xattr -d com.apple.quarantine srtstripper` (or open it once via right click, Open).

### Windows installer (x86_64, ARM64)

x86_64:

    curl.exe -L -O https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-windows-x86_64-setup.exe
    .\srtstripper-windows-x86_64-setup.exe

ARM64:

    curl.exe -L -O https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-windows-aarch64-setup.exe
    .\srtstripper-windows-aarch64-setup.exe

The installer is per-user and needs no admin rights. It installs to `%LOCALAPPDATA%\Programs\srtstripper` by default, and the install folder can be changed in the wizard. It adds the install folder to the user PATH (the task can be cleared during setup), creates a `srtstripper` shortcut in the Start Menu so the app shows up in All apps, and registers an uninstaller in Settings > Apps. There is no license page. Taskbar pinning cannot be offered: Windows does not allow an installer to pin an app to the taskbar, that is a user action. Silent install: `srtstripper-windows-x86_64-setup.exe /VERYSILENT` (add `/TASKS=` to skip the PATH entry); silent uninstall: `unins000.exe /VERYSILENT` in the chosen install folder. The setups are not code-signed, so SmartScreen may ask for confirmation.

### Windows (PowerShell or cmd)

No installer, standalone exe:

x86_64:

    curl.exe -L -o srtstripper.exe https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-windows-x86_64.exe

ARM64:

    curl.exe -L -o srtstripper.exe https://github.com/chezhenkie/srt-subtitle-stripper/releases/latest/download/srtstripper-windows-aarch64.exe

## Build from source

    cd srtstripper
    cargo build --release --locked

## CI and releases

GitHub Actions runs fmt, clippy (`-D warnings`), build, unit tests, the 97-case golden regression suite and an end-to-end smoke on Linux (x86_64 and ARM64), Windows (x86_64 and ARM64), macOS and statically linked musl builds for Alpine and other non-glibc systems, and uploads the binaries as artifacts. Pushing a tag `v*` publishes a GitHub release with the binaries and `SHA256SUMS` attached.

## Development

    cd srtstripper
    cargo test --release

Unicode tables for `\w`, `\d`, `\s`, `isspace`, `splitlines` and cp1252 are generated into `srtstripper/src/tables.rs` by `srtstripper/tools/gen_tables.py`; do not edit the generated file by hand. The regression suite in `srtstripper/tools/` runs the binary over modes and fixtures and compares exit codes, output text and every produced file against checked-in expected results; `--update` regenerates them.

## Project docs

- Requirements and design constraints: `REQUIREMENTS.md`.
- Release history: `CHANGELOG.md`.
- License: MIT, see `LICENSE`.
