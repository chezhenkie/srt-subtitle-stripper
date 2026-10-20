# Requirements

Requirements for srtstripper, a standalone Rust CLI that strips non-alphabetic lines from SRT/text subtitle files.

## Functional requirements

- FR1: Strip non-alphabetic lines from SRT/text files and write a cleaned copy; identical input and options always produce identical output bytes.
- FR2: Default mode keeps every line containing at least one letter, drops index and timestamp lines, keeps blank lines as separators, collapses runs of blank lines to one and trims trailing blanks. If dropping scaffolding lines would leave two text paragraphs adjacent, a blank line is inserted between them. Consecutive repeated text lines collapse to the first occurrence; blank separators between repeats shrink to one.
- FR3: `--timecode` recognizes SRT cue timestamps matching `(\d{1,2}):(\d{2}):(\d{2})[,.]\d{3}\s*-->`, merges cue text into one block per cue with an `[HH:MM:SS]` line above the text, emits text outside cues as its own block, and separates blocks with a blank line. A blank line directly after a cue timestamp is part of the cue's leading whitespace and does not clear the stamp. Rolling captions repeat words that are already on screen, so each paragraph is trimmed against the text already emitted: the longest word-boundary prefix that equals the end of that text is removed and only the new words are written under the cue's own stamp. A paragraph fully covered at the end of the emitted text is dropped. The comparison never includes the stamp.
- FR4: `--numbered` produces the SRT look without timecodes: a number line above each text block, blank lines kept between blocks. Consecutive repeated text lines collapse to the first occurrence, and a block whose merged text equals the last kept block is dropped whole. It is mutually exclusive with `--timecode`.
- FR5: Repeat collapsing applies to all modes. In `--timecode` the comparison is on the merged paragraph text only, never on the stamp. Overlap shorter than 8 characters is ignored, the overlap search covers the last 1024 bytes of emitted text, and matches must start and end on word boundaries.
- FR6: Output naming follows the scheme: `"<stem> - alpha.txt"`, `"<stem> - timecodes.txt"`, `"<stem> - numbered.txt"`; `--out` overrides; parent directories are created; an empty result still creates (truncates) the file.
- FR7: Decoding order: utf-8-sig (BOM stripped), then strict cp1252 (failing on undefined bytes 0x81 0x8D 0x8F 0x90 0x9D), then utf-8 with permissive replacement decoding (invalid sequences are dropped per a fixed grouping rule). Output is UTF-8; CRLF is used if the input contains CRLF, LF otherwise.
- FR8: Line splitting follows Unicode `splitlines` semantics (the full break set including U+0085, U+2028 and U+2029); line filtering uses the `[^\W\d_]` letter test, Unicode whitespace for blank detection and standard strip trimming.
- FR9: CLI behavior: the mode flags and `--out`, prefix matching of long options with ambiguity errors, usage and exit behavior (0 success, 2 usage error or input not found, 1 I/O error) and a `PASS: mode=..., wrote N lines from M input lines -> path` summary on stdout. Argument-level usage errors print the usage line, a `srtstripper: error: <msg>` line and an examples block showing one valid invocation per mode.
- FR12: Several input files may be given (Windows drag-and-drop onto the exe passes each dropped file as a bare path). Every input is processed independently with the same flags; each input prints its own PASS or FAIL line; the process exit code is the worst of the run (2 beats 1). `--out` is rejected when more than one input is given.
- FR13: An optional `srtstripper.json` file in the exe's directory selects the mode when no mode flag is given on the command line. It is a flat JSON object; the only defined key is `mode` with the values `text` (default), `timecode` and `numbered`. Unknown keys are ignored so later versions can add keys. A missing file means the default text mode. A malformed file, a non-string `mode` value or an unknown mode value is an error: a `FAIL:` line on stderr and exit code 2. Command line flags override the config values.
- FR10: Timecode fields accept Unicode decimal digits; the emitted `[HH:MM:SS]` stamp formats only the hour field as two ASCII digits while the minute and second fields keep their original digits.
- FR11: Combining `--timecode` with `--numbered` is rejected with a usage error.

## Delivery requirements

- DR1: Standalone executables for Windows, Linux and macOS with no runtime dependencies.
- DR2: No console window may appear when the Windows exe is launched by another application; interactive console use still prints PASS/FAIL, and redirected stdout/stderr is always honored.
- DR3: Builds and tests run on GitHub Actions; official binaries are produced by CI and attached to tagged releases, never hand-built.
- DR4: The Windows exe carries filled-in Properties/Details metadata: company, description, version, product, copyright and original filename.
- DR5: Public repository under the MIT license.
- DR6: Automated tests cover behavior: unit fixtures, a regression suite over the fixture set comparing exit codes, output text and produced files against checked-in expected results, and Windows acceptance checks for the GUI subsystem and no-console operation.

## References

- `README.md`: usage, install instructions and known presentation deviations.
- `CHANGELOG.md`: release history.
