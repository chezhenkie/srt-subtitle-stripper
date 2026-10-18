# Requirements

Requirements for srtstripper, a standalone Rust CLI that strips non-alphabetic lines from SRT/text subtitle files. Ported from the author's earlier Python script (`deprecated-py-src/strip_srt.py`).

## Functional requirements

- FR1: Strip non-alphabetic lines from SRT/text files and write a cleaned copy; identical input and options always produce identical output bytes.
- FR2: Default mode keeps every line containing at least one letter, drops index and timestamp lines, keeps blank lines as separators, collapses runs of blank lines to one and trims trailing blanks. If dropping scaffolding lines would leave two text paragraphs adjacent, a blank line is inserted between them.
- FR3: `--keep-timecodes` recognizes SRT cue timestamps matching `(\d{1,2}):(\d{2}):(\d{2})[,.]\d{3}\s*-->`, merges cue text into one paragraph per cue with an `[HH:MM:SS]` prefix, emits text outside cues as its own paragraph, and separates paragraphs with a blank line.
- FR4: `--numbered` prefixes every kept text line with a 5-digit counter (`00001`, `00002`, ...); blank separator lines stay unnumbered.
- FR5: `--numbered-only` produces the SRT look without timecodes: a number line above each text block, blank lines kept between blocks. It is mutually exclusive with `--numbered` and is rejected together with `--keep-timecodes`.
- FR6: Output naming follows the scheme: `"<stem> - alpha.txt"`, `"<stem> - timecodes.txt"`, `"<stem> - numbered.txt"`, with `" numbered"` appended to the suffix when `--numbered` stacks on another mode; `--out` overrides; parent directories are created; an empty result still creates (truncates) the file.
- FR7: Decoding order: utf-8-sig (BOM stripped), then strict cp1252 (failing on undefined bytes 0x81 0x8D 0x8F 0x90 0x9D), then utf-8 with permissive replacement decoding (invalid sequences are dropped per a fixed grouping rule). Output is UTF-8; CRLF is used if the input contains CRLF, LF otherwise.
- FR8: Line splitting follows Unicode `splitlines` semantics (the full break set including U+0085, U+2028 and U+2029); line filtering uses the `[^\W\d_]` letter test, Unicode whitespace for blank detection and standard strip trimming.
- FR9: CLI behavior: the mode flags and `--out`, prefix matching of long options with ambiguity errors, usage and exit behavior (0 success, 2 usage error or input not found, 1 I/O error) and a `PASS: mode=..., wrote N lines from M input lines -> path` summary on stdout.
- FR10: Timecode fields accept Unicode decimal digits; the emitted `[HH:MM:SS]` stamp formats only the hour field as two ASCII digits while the minute and second fields keep their original digits.

## Delivery requirements

- DR1: Standalone executables for Windows, Linux and macOS with no runtime dependencies.
- DR2: No console window may appear when the Windows exe is launched by another application; interactive console use still prints PASS/FAIL, and redirected stdout/stderr is always honored.
- DR3: Builds and tests run on GitHub Actions; official binaries are produced by CI and attached to tagged releases, never hand-built.
- DR4: The Windows exe carries filled-in Properties/Details metadata: company, description, version, product, copyright and original filename.
- DR5: Public repository under the MIT license.
- DR6: Automated tests cover behavior: unit fixtures, a differential suite over the fixture set, and Windows acceptance checks for the GUI subsystem and no-console operation.

## References

- `python-to-rust-refactor-pitfalls.md`: implementation traps this port must avoid (buffering, allocation caching, integer semantics, text and byte handling, error handling).
- `README.md`: usage, install instructions and known presentation deviations.
- `CHANGELOG.md`: release history.
