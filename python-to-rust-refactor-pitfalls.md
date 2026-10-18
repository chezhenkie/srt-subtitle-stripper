# Pitfalls when refactoring from Python to Rust

Python's runtime hides a lot of work; Rust exposes it. If you port code 1:1 you lose many of those hidden optimizations and the Rust version can end up slower or incorrect. This doc lists the traps, with fixes.

## 1. The big one: automatic write caching in Python, none in Rust

### Python side
`open()` never returns a raw file object unless you explicitly pass `buffering=0`, and that is "only allowed in binary mode": you then get the raw `io.FileIO` stream back (https://docs.python.org/3/library/functions.html#open). By default you get a buffered wrapper, and in text mode that is an `io.TextIOWrapper` over a buffered binary stream (same page). The wrapper aggregates small writes into a buffer and only issues real OS writes when the buffer fills, on `close()`, or on explicit `flush()`.
The buffer size is `io.DEFAULT_BUFFER_SIZE`, and the value changed in Python 3.14: `Modules/_io/_iomodule.h` defines `(8 * 1024)` on the 3.13 branch and `(128 * 1024)` on the 3.14 branch (https://raw.githubusercontent.com/python/cpython/3.13/Modules/_io/_iomodule.h vs https://raw.githubusercontent.com/python/cpython/3.14/Modules/_io/_iomodule.h); both local runtimes report 131072 (measured on 3.14.6 and 3.14.4). The change came out of the buffered I/O rework discussed in 2025
(https://discuss.python.org/t/reworking-buffered-i-o-in-cpython/90019).

So this Python loop does roughly ONE syscall per buffer load - 8 KiB through Python 3.13, 128 KiB from 3.14 - not one per write:

```python
f = open("out.txt", "w")       # actually a TextIOWrapper over BufferedWriter
for item in items:
    f.write(f"{item}\n")       # lands in the buffer, not the OS
f.close()
```

Measured: after 200 writes of 1000 bytes in binary mode, only 131000 of the 200000 bytes had reached the OS before `close()`; text mode held 74000 bytes back the same way.

### Rust side
`std::fs::File` does NOT buffer: "File does not buffer reads and writes. For efficiency, consider wrapping the file in a BufReader or BufWriter when performing many small read or write calls, unless unbuffered reads and writes are required" (https://doc.rust-lang.org/std/fs/struct.File.html). The Rust Performance Book states it plainly: "Rust file I/O is unbuffered by default. If you have many small and repeated read or write calls to a file or network socket, use BufReader or BufWriter"
(https://nnethercote.github.io/perf-book/io.html).

A naive 1:1 port of the loop above runs `file.write_all(...)` per iteration and pays one syscall PER WRITE (one ~10 byte line each). Measured with the same workload: a raw Rust `File` had all 200000 bytes on disk immediately, while the Python version still held a buffer (see above). This is the "many writes in a loop where 1 cache action would be enough" trap: Python cached it for you, Rust makes you do it yourself. The fix is one buffered wrapper around the file, applied once, not a change to
the loop body:

```rust
use std::io::{BufWriter, Write};

let mut out = BufWriter::new(std::fs::File::create("out.txt")?); // 8 KiB default
for item in &items {
    writeln!(out, "{}", item)?;   // lands in the buffer
}
// one real write of what remains happens here, or at explicit flush:
out.flush()?;
```

`BufWriter::new` defaults to 8 KiB ("The default is currently 8 KiB, but may change in the future", https://doc.rust-lang.org/std/io/struct.BufWriter.html); use `BufWriter::with_capacity(128 * 1024, f)` if you want to match what CPython 3.14 does for you. Measured: the same 200 x 1000 B workload left 192000 of 200000 bytes in the default BufWriter until the explicit flush.

### Sub traps inside this one
- Wrong fix: allocating a new `BufWriter` inside the loop, or reopening the file per line. Wrap once, outside the loop.
- Partial writes. Raw `write()` may write fewer bytes than requested; use `write_all` (https://doc.rust-lang.org/std/fs/struct.File.html, whose examples use `write_all`).
- Drop errors are swallowed. "It is critical to call flush before BufWriter is dropped. Though dropping will attempt to flush the contents of the buffer, any errors that happen in the process of dropping will be ignored" (https://doc.rust-lang.org/std/io/struct.BufWriter.html). Python's `close()` propagates errors from the buffered flush; Rust lives by this only if you explicitly call `flush()` and check the Result. Related open issue: rust-lang/rust#136025, "Docs on safety of BufWriter are
misleading" (https://github.com/rust-lang/rust/issues/136025).
- `println!` in a loop is the same trap for stdout. Rust stdout goes through a `LineWriter` unconditionally (the std source has no tty check), so each line is flushed on its newline even when stdout is a pipe or file (https://doc.rust-lang.org/src/std/io/stdio.rs.html). Measured examples from blogs: a `1..1_000_000` println! loop at ~1.08 s line buffered vs ~0.41 s block buffered
(https://hackyourmom.com/en/osvita/poglyblene-porivnyannya-stdout-i-stderr-buferyzacziya-produktyvnist-ta-pryklady-v-rust-chastyna-2), and ~17.6 s for a 500,000-line println! loop vs ~3.7 s with `stdout().lock()` plus `BufWriter` (https://ericswpark.com/blog/2025/2025-01-23-buffering-by-block-in-rust). Numbers are machine specific (neither post lists machine specs), so treat them as illustrative ratios, not absolutes.
- stderr: Rust's stderr is unbuffered ("This handle is not buffered", https://doc.rust-lang.org/std/io/fn.stderr.html), while Python's stderr is line-buffered since 3.9 ("Changed in version 3.9: Non-interactive stderr is now line-buffered instead of fully buffered", https://docs.python.org/3/library/sys.html#sys.stderr). A port that swaps which side logs can change syscall counts a lot.
- Same shape one level up: anywhere the Python code did many small writes through a socket, a csv writer, or a subprocess pipe, the Python runtime buffered it; in Rust either wrap the writer in BufWriter or build one big buffer and write it once.

### Rule
Port the loop; wrap the ENDPOINT in a BufWriter once; flush once at the end; explicit flush before drop; use write_all. When in doubt, benchmark syscalls with strace/Process Monitor, not wall time. If the port already builds the whole payload in memory anyway (the str.join shape), a single write_all of that buffer is the same shape - do not wrap one big write in a BufWriter.

## 2. String building in loops

- Python strings are immutable, but CPython quietly mutates them as an optimization: "If the string is modifiable (has only 1 reference and is not interned), then it will try to append in place" (https://austinhenley.com/blog/pythonstringsaremutable.html), and that append path runs through `unicode_resize`, which reuses the allocation if the new size fits and allocates otherwise ("unicode_resize() will see if it will fit or if a new allocation needs to be made", same page).
- The optimization is conditional, and that conditionality is the trap: the PyPy blog states repeated concatenation "is in principle also quadratic in CPython, but CPython has an optimization that makes them sometimes not quadratic... it only triggers if the reference count of `b` is 1, in which case it uses `realloc`" (https://www.pypy.org/posts/2023/01/string-concatenation-quadratic.html). Store the accumulator anywhere, or run under a runtime without the trick, and the loop can go quadratic.
The post's conclusion: "don't use repeated concatenations in a loop!", use a list plus `str.join`.
- Rust's `+` always reuses the buffer: "This consumes the `String` on the left-hand side and re-uses its buffer (growing it if necessary). This is done to avoid allocating a new `String` and copying the entire contents on every operation, which would lead to *O*(*n*^2) running time when building an *n*-byte string by repeated concatenation" (https://doc.rust-lang.org/std/string/struct.String.html). `+` is implemented as `push_str` (https://doc.rust-lang.org/src/alloc/string.rs.html), and both
reuse the same allocation with geometric growth, so an append-only `s = s + part` loop is amortized linear (measured: 100,000 appends caused only 4 buffer-address changes, identical to `push_str`).
- What IS quadratic in Rust is building a fresh `String` every iteration, e.g. `s = format!("{}{}", s, part)` copies the whole accumulator each pass. Also note the literal example `"a" + "b"` does not compile at all: E0369, "cannot add `&str` to `&str`" (measured); the left side must be an owned `String`.
- Idiomatic and cheapest: one `String`, `with_capacity`/`reserve` when the size is known, then `push_str` in the loop (https://doc.rust-lang.org/std/string/struct.String.html#method.with_capacity), which removes the few growth reallocations; the Python `"".join(list_of_parts)` shape the PyPy post recommends maps to collecting parts and joining once, and is linear either way.

## 3. Allocation per iteration, where Python had caches

CPython has many allocation caches that make naive loops cheap:

- Small object allocator (pymalloc) serves allocations up to 512 bytes out of pools and puts freed blocks back into a free list for reuse (https://dev.to/jamesli/python-memory-optimization-how-cpythons-memory-pool-works-47b9).
- Since Python 3.11, call frames are allocated on a per-thread stack and the `PyFrameObject` wrapper is only materialized when Python code can see it, so call-heavy code no longer pays a heap allocation per call (https://github.com/python/cpython/blob/main/InternalDocs/frames.md); before 3.11 a frame object of a suitable size was cached per code object (https://cosmicpercolator.com/2012/05/23/zombieframes-a-gratuitous-optimization).
- Small ints are preallocated objects: "CPython keeps an array of integer objects for all integers between -5 and 256" (https://docs.python.org/3.14/c-api/long.html; measured on 3.14.6: `int("256")` twice returns the same object, `int("257")` twice does not). Identifier-like string constants are interned at compile time (CPython interns constants matching `[a-zA-Z0-9_]`, https://github.com/python/cpython/blob/main/Objects/codeobject.c).

Rust has none of this for your own types with the default system allocator: the 1:1 port pays an allocation per iteration where Python reused an existing object. Guard rails:
- No `Vec::new()`, `String::new()`, `String::from(...)`, `format!(...)`, `HashMap::new()`, `.clone()`, or `to_string()` inside a hot loop when it could be hoisted and reused. (`Vec::new()`/`String::new()` themselves do not allocate until first use - https://doc.rust-lang.org/std/vec/struct.Vec.html#method.new - but constructing and filling them per iteration does.) Reuse with `clear()` instead of recreating structures.
- `.clone()` used to satisfy the borrow checker is the classic accretion path: it is listed as an anti-pattern when a borrow would do ("If a clone is used to make a borrow checker error disappear, that's a good indication this anti-pattern may be in use", https://rust-unofficial.github.io/patterns/anti_patterns/borrow_clone.html; loop-bound clones: "Auto-cloning inside loops... prefer to call .cloned() or .copied() at the end of the iterator",
https://github.com/apollographql/rust-best-practices/blob/main/book/chapter_01.md). Deep clones allocate and copy all nested fields, while clone is cheap only for Copy types and Arc refcount bumps (https://hamy.xyz/blog/2026-02_the-problem-with-clones-in-rust). Note that clippy's `redundant_clone`, the lint that catches needless clones of owned values, is allow-by-default in the nursery group, so it only fires if enabled explicitly
(https://rust-lang.github.io/rust-clippy/master/index.html#redundant_clone).
- Know your final size and ask for it once: pushing 20 elements one at a time costs "four allocations (for capacities of 4, 8, 16, and 32)" under the quasi-doubling strategy (https://nnethercote.github.io/perf-book/heap-allocations.html; measured: same [4, 8, 16, 32]), while `Vec::with_capacity` / `reserve` / `String::with_capacity` make it one allocation. `collect()` may preallocate from the iterator's size hint ("may use any or none of the following strategies... preallocate based on
Iterator::size_hint()", https://doc.rust-lang.org/std/vec/struct.Vec.html), and `push` on an unknown length is amortized O(1) ("Takes amortized O(1) time", same page).
- Note the one place std does cache: `HashMap`'s `RandomState` does not fetch entropy per map; "it caches a key per thread and increments it" (https://ibraheem.ca/posts/random-number-generator-in-rust-std). This only matters if you implement your own hasher/state.

## 4. Integer semantics changed, silently

- Python ints are arbitrary precision: "All integers are implemented as 'long' integer objects of arbitrary size" (https://docs.python.org/3.14/c-api/long.html); CPython stores them as "a number of 30- or 15-bit digits, depending on the platform" (https://raw.githubusercontent.com/python/cpython/main/Include/cpython/longintrepr.h).
- Rust ints are fixed width and overflow behavior differs by build profile: "in debug mode, arithmetic (+, -, etc.) on signed and unsigned primitive integers is checked for overflow, panicking if it occurs, and, in release mode, overflow is not checked and is specified to wrap as two's complement" (https://huonw.github.io/blog/2016/04/myths-and-legends-about-integer-overflow-in-rust/; the decision is RFC 560, same page; a worked breakdown:
https://sec3.dev/blog/understanding-arithmetic-overflow-underflows-in-rust-and-solana-smart-contracts/). Measured: `i32::MAX + 1` panicked in a debug build and printed -2147483648 in a release build.
- Consequence: a loop that accumulates a counter or hash that always fit in Python can silently wrap in a Rust release build, and the same code panics in debug; there is no single behavior shared by both profiles. Decisions: use wider types (`i64`/`u64`/`usize`), or `checked_*` / `saturating_*` / `wrapping_*` explicitly, or set `overflow-checks = true` in the release profile if the workload is not perf critical in that spot
(https://doc.rust-lang.org/cargo/reference/profiles.html#overflow-checks). If the Python code genuinely relies on arbitrary precision, porting to a fixed width is a design change: use a bignum crate such as `num-bigint` (https://docs.rs/num-bigint).
- Casting across widths via `as` truncates without error (https://doc.rust-lang.org/reference/expressions/operator-expr.html). Use `try_into()` (and fallible `From`/`TryFrom`) where the range matters.

## 5. Text and bytes are not the same thing

- Python `str` is a sequence of code points with O(1)-ish indexing: CPython's flexible representation stores 1, 2, or 4 bytes per code point depending on the widest character, "while still allowing efficient indexing of strings containing non-BMP characters" (https://peps.python.org/pep-0393/). Rust `String`/`str` is UTF-8 BYTES: `s[0]` does not compile (measured: E0277, "the type `str` cannot be indexed by `{integer}`"), and byte slicing panics unless both ends land on char boundaries ("Panics
if begin or end does not point to the starting byte offset of a character", https://doc.rust-lang.org/std/primitive.str.html; measured: slicing inside a multibyte char panics with "is not a char boundary"). Iterate with `chars()` or work on `bytes()` when the data is what matters.
- Python's `open(..., encoding="...")` gave you a `TextIOWrapper` decoder for free; the default encoding is platform dependent and `newline=None` translates `\n` to `os.linesep` on write (https://docs.python.org/3/library/functions.html#open). In Rust, reading gives you bytes and decoding is explicit: `read_to_string` errors on invalid UTF-8 ("If the data in this stream is not valid UTF-8 then an error is returned", https://doc.rust-lang.org/std/io/trait.Read.html#method.read_to_string),
`String::from_utf8` "Returns Err if the slice is not UTF-8" (https://doc.rust-lang.org/std/string/struct.String.html#method.from_utf8), and for non-UTF-8 sources use a crate like `encoding_rs` (https://docs.rs/encoding_rs/latest/encoding_rs/). Decode errors Python deferred to encode()/decode() time become explicit Rust errors at the boundary.
- Memory overhead per string shrinks a lot: CPython pays a full Python object header per value; Rust pays only the bytes' buffer plus a three-word header ("A String is made up of three components: a pointer to some bytes, a length, and a capacity", https://doc.rust-lang.org/std/string/struct.String.html), or a two-word fat pointer for a borrowed slice ("As slices store the length of the sequence they refer to, they have twice the size of pointers to Sized types",
https://doc.rust-lang.org/std/primitive.slice.html). This means ported code often becomes both faster and dramatically smaller in memory, IF you fix items 1 and 3.

Two traps in this area have their own sections below: Python's character classes and line splitting (section 8) and decode error handlers (section 9).

## 6. Errors, control flow, and the fallibility that Python hid

- Python's runtime raised exceptions for missing files, bad conversions, math errors. In Rust those become a mix: missing files and bad conversions are `Result`s you must handle, but integer division by zero panics ("For integer types, division by zero panics", https://doc.rust-lang.org/reference/expressions/operator-expr.html), float division follows IEEE 754 (inf/NaN instead of an error; the f32 docs describe the IEEE-754-2008 conformance, https://doc.rust-lang.org/std/primitive.f32.html), and
out-of-bounds indexing panics. Do not "handle" the Result half by sprinkling `.unwrap()`: a panic prints the message plus the exact file:line:column, but the call stack is only printed when `RUST_BACKTRACE` is set ("setting the RUST_BACKTRACE environment variable to any value except 0"), and the location points at where the panic was raised, not where the bug is (https://doc.rust-lang.org/book/ch09-01-unrecoverable-errors-with-panic.html; measured: a debug overflow panic printed `panicked at
ovf.rs:3:5` plus the RUST_BACKTRACE hint). Use `thiserror`/`anyhow` style error propagation so failures are diagnosable like Python exceptions were.
- Python `for` loops over `range` map to Rust range iterators, but Python's `range` supports negative steps and arbitrary-precision bounds (https://docs.python.org/3/library/stdtypes.html#range), while Rust ranges are half-open (`a..b` excludes `b`, https://doc.rust-lang.org/std/ops/struct.Range.html) and there is no negative-step sugar: descending iteration is `.rev()` on a `DoubleEndedIterator` and stepping is `.step_by(n)` with a positive `usize`
(https://doc.rust-lang.org/std/iter/trait.DoubleEndedIterator.html, https://doc.rust-lang.org/std/iter/struct.StepBy.html). Check all range and slicing ports for off-by-one; the type system catches many but not the semantic ones.

## 7. Benchmark and build profile pitfalls

- Never judge a Rust port from a `cargo run` without `--release`. The dev profile defaults to `opt-level = 0`, `debug-assertions = true`, `overflow-checks = true`; the release profile defaults to `opt-level = 3`, `debug-assertions = false`, `overflow-checks = false` (https://doc.rust-lang.org/cargo/reference/profiles.html). Debug builds can therefore be slower than Python - "Debug builds in Rust include bounds checking, overflow checking, and no optimization: they can be slower than Python"
(https://rustify.rs/articles/i-rewrote-my-python-script-in-rust-2026, a vendor blog). Careful with that quote's wording: bounds checks exist in all profiles, only the optimizer removes provable ones ("By default, accesses to container types such as slices and vectors involve bounds checks in Rust", https://nnethercote.github.io/perf-book/bounds-checks.html); what really differs by profile is optimization level, debug assertions, and overflow checks. The cited rewrite measured its ~47x speedup
against a release build (same vendor article).
- Set `overflow-checks = true` in the release profile for correctness-sensitive numeric code so ported Python assumptions surface as panics instead of silent wraps (https://doc.rust-lang.org/cargo/reference/profiles.html#overflow-checks; see item 4). This does not restore arbitrary precision - use a bignum crate when you truly need it.
- Run timing comparisons from a native filesystem, not a mounted network or 9p path.

## 8. Python's character classes and line splitting are not Rust's

- re `\w`, re `\d`, re `\s`, `str.isspace()`, `str.splitlines()` and `str.strip()` are defined by CPython's Unicode data, and the Rust std lookalikes use different sets. Measured: `'\x1c'.isspace()` is True in Python 3.14, while Rust's `char::is_whitespace` follows the Unicode White_Space property and returns false for U+001C..U+001F.
- The Python whitespace set measured on 3.14.6 is 0x09-0x0D, 0x1C-0x20, 0x85, 0xA0, 0x1680, 0x2000-0x200A, 0x2028-0x2029, 0x202F, 0x205F, 0x3000 (10 ranges); it is what `isspace`, `strip` and re `\s` all agree on in that runtime.
- `str.splitlines()` breaks on \n \v \f \r \x1c \x1d \x1e \x85 U+2028 U+2029, treats \r\n as one break, and never yields a trailing empty line after a final break; Rust's `str::lines()` only understands \n and \r\n. A line-based tool ported with `lines()` silently differs on any input containing the other seven breaks.
- Python's `int()` accepts every Unicode decimal digit (`int("\u0663") == 3`), and re `\d` matches Nd where adjacent blocks merge into single runs (mathematical digits 0x1D7CE..0x1D7FF are 50 code points in one run); Rust's `u32::from_str` is ASCII-only and rejects all of them.
- re `[^\W\d_]` ("has a letter") counts No and Nl: superscript `\u00b2`, vulgar `\u00bd` and Roman `\u2163` pass, Arabic-Indic `\u0663` does not; Rust's `char::is_alphabetic` implements the Alphabetic property and answers differently on several of these.
- The fix used in this port: generate the tables from the target interpreter instead of trusting Rust's methods - 727 letter ranges, 71 digit ranges, 10 space ranges, plus a 21k-code-point fixture for boundary tests - and record `sys.version` and `unicodedata.unidata_version` in the generated header (frozen at CPython 3.14.6, Unicode 16.0.0).

### Rule
Freeze every Python character-class decision into generated tables keyed to the interpreter's Unicode version, cover them with boundary fixtures, and never substitute a Rust std method for a Python-set question.

## 9. Decoding errors: Python handlers are not from_utf8_lossy

- `data.decode("utf-8", "replace")` emits ONE U+FFFD per error event, and the event length depends on the failure kind, per Objects/stringlib/codecs.h: invalid start byte 1 byte, invalid first continuation 1 byte, invalid second continuation 2 bytes, invalid third continuation 3 bytes, truncated at end of data swallows the whole remaining sequence.
- Rust's `String::from_utf8_lossy` groups differently (WHATWG/Unicode maximal subpart via utf8_error_len). Measured: b"\x81\xF0\x9F" decodes to two U+FFFD in CPython and three in Rust; b"\xF0\x9F\x92" truncated at EOF is one U+FFFD in CPython.
- Real files also pass through the whole decode chain: the original tried "utf-8-sig", then "cp1252", then "utf-8" with replace. cp1252 has five undefined bytes (0x81, 0x8D, 0x8F, 0x90, 0x9D) whose presence forces the lossy path, and a lone BOM in otherwise invalid utf-8 decodes as the mojibake characters because the cp1252 attempt succeeds first.
- The fix used here: a hand-rolled lossy decoder mirroring the table above, checked against decoder fixtures generated from the interpreter (truncated at EOF, F4 90 range violation, ED A0 surrogate, lone continuation runs, overlong C0, BOM-in-invalid-utf-8).

### Rule
Replicate the original's decode chain and error-handler grouping; generate invalid-byte fixtures from the interpreter and compare decoded strings.

## 10. CLI surface parity: argparse, paths, stdout text

- argparse behavior is part of the contract when a Rust binary replaces a Python CLI: unknown options are deferred (so "the following arguments are required: input" fires before "unrecognized arguments"), and -h wins inside short clusters (-hx prints help, -xh does not).
- Long options match by unambiguous prefix with an "ambiguous option: --num could match --numbered, --numbered-only" error; --out=value and --out value differ (the latter refuses a token that looks like another option), and every usage error exits 2 with the message on stderr.
- Probe it instead of reading argparse internals: run the original with an edge-case argv matrix and record rc/stdout/stderr (used here: 28 cases incl. ['--out','--numbered'], ['--num','x.srt'], ['--numbered=x','x.srt'], ['-hx'], ['--bogus','-h']).
- pathlib is not Rust Path: `Path.stem` behaves like os.path.splitext on the name ("foo." -> "foo", "a..b" -> "a.", ".hidden" and "..." keep the whole name) and `Path()` strips trailing separators; on Windows, Win32 itself normalizes trailing dots and spaces in file names and both languages inherit that. Freeze name-derived output paths with a fixture table.
- stdout text is platform-dependent in Python: on Windows the piped stdout is encoded with the ANSI codepage (0xEB for "u-umlaut" on the test machine) and text-mode writes translate \n to \r\n, while Rust writes UTF-8 with LF. File outputs stayed byte-identical in this port; if stdout byte parity matters, replicate the codepage logic, otherwise document the deviation and normalize only message streams in the differential harness.

### Rule
Treat argv edge cases, exit codes, path derivation and stdout encoding as part of the port, freeze them with probes or tables, and compare them mechanically.

## 11. Console behavior when another application launches the port

- A Python script runs under python.exe (console subsystem), so a console exists and interactive output plus shell waiting just work. A Rust exe can be console or GUI subsystem, and the choice is user-visible: GUI subsystem with `#![cfg_attr(windows, windows_subsystem = "windows")]` guarantees no console window is ever allocated when a GUI app spawns it (no flash), but interactive cmd/PowerShell no longer wait for it and stdout goes nowhere unless a parent provided handles.
- Keep both behaviors: when the inherited stdout/stderr handles are invalid, attach to the parent console (AttachConsole(ATTACH_PARENT_PROCESS), CreateFileW("CONOUT$"), SetStdHandle) before any print; when they are valid (pipe or file from the caller), leave them alone so capture keeps working.
- Measured on the shipped exe: PE subsystem 2 (GUI); DETACHED_PROCESS with DEVNULL handles exits 0 and still writes its output file; cmd /c redirection, Start-Process -RedirectStandardOutput and Python subprocess all capture rc/stdout/files exactly.

### Rule
Pick the subsystem from the deployment requirement (window suppression vs shell waiting), rebind only invalid console handles, and verify with a no-console spawn test plus a redirected-handle capture test.

## 12. Porting ritual checklist

Before merging a Python to Rust port, verify each:

- [ ] Writers are wrapped in `BufWriter` once, OUTSIDE the loop; explicit `flush()` before drop; `write_all` not bare `write`.
- [ ] Socket, csv, zip, and stderr producers reviewed for the same buffering shape. Rust stderr is unbuffered (https://doc.rust-lang.org/std/io/fn.stderr.html) while Python's has been line-buffered since 3.9 (https://docs.python.org/3/library/sys.html#sys.stderr), so swapping which side logs can shift syscall counts. stdout loops use `stdout().lock()` wrapped in a `BufWriter`, not `println!` per line; locking alone does not change buffering (https://doc.rust-lang.org/std/io/struct.Stdout.html).
- [ ] Hot loops: no `Vec::new`/`String::new` plus fill, no `format!`, `clone()`, `to_string()`, `HashMap::new` per iteration; structures hoisted, reused, and `with_capacity`/`reserve` called when size is known or hinted. No self-concatenation via `format!` (item 2).
- [ ] Integer math: no untyped `as` casts on ports of bignum code; overflow behavior pinned via types, `overflow-checks`, or explicit checked/saturating ops; tests cover the boundaries the Python code could not hit.
- [ ] String/byte semantics: byte offsets vs code points confirmed; encoding decoding explicit and tested with invalid input.
- [ ] Release build (`--release`) used for any performance claim; cargo bench or criterion for the before/after numbers.
- [ ] Error handling: every former Python exception path maps to a Result branch that is actually tested, or to a documented, intentional panic - never a bare unwrap.
- [ ] If the Python code was dynamically dispatching on data shapes at runtime, check the Rust version still handles the union, not just the shapes that happened to show up.
- [ ] Character classes and line splitting frozen into generated tables keyed to the interpreter's Unicode version, boundary fixtures passing, no Rust std char method standing in for a Python set (section 8).
- [ ] Decode chain and error-handler grouping replicated, with fixtures generated from the interpreter for truncated, overlong, surrogate and undefined-byte inputs (section 9).
- [ ] If the binary replaces a Python CLI: argv edge matrix probed, exit codes, path derivation and stdout encoding checked (section 10).
- [ ] Golden differential test: both implementations run the same fixtures; exit code, stdout, stderr and every produced file compared by hash; run on the primary platform and on the one with different text conventions (Windows).
- [ ] Windows exe: subsystem choice deliberate, redirected handles preserved, no-console spawn test and capture test pass (section 11).

## 13. What this does NOT mean

- Rust's compile-time dispatch and zero-cost abstractions are real: after you fix items 1 to 5, typical CPU-bound ports see very large wins, though published numbers are illustrative and often commercial: a Rust bootcamp blog measures ~47x on a 2 GB log scan and "nearly 50x" on a 10 GB file against a release build (https://rustify.rs/articles/i-rewrote-my-python-script-in-rust-2026), and an SEO content site lists "25x to 100x" for CPU-bound tasks (https://tech-insider.org/python-vs-rust-2026).
Measure your own workload.
- The point of this doc is not "Rust is slow", it is "a 1:1 mechanical port throws away the optimizations Python's runtime did silently, and Rust gives you the tools to do them properly". Do them.
