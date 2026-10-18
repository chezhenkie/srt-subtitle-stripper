//! srtstripper - strip non-alphabetic lines from SRT/text files.
//!
//! Standalone Rust port of the Python script now kept in
//! `deprecated-py-src/strip_srt.py`; outputs are byte-for-byte identical.
//! No runtime dependencies, no external crates.
//!
//! Windows behavior: the exe is built as a GUI-subsystem binary so no console
//! window ever appears when another app launches it. When launched from a
//! console it attaches to the parent console to print PASS/FAIL. stdout or
//! stderr handles provided by a parent (pipes, files) are left untouched.
//!
//! Python-autocaching decisions (see python-to-rust-refactor-pitfalls.md):
//! - the whole output is built in one `String` (like CPython's str.join) and
//!   written with a single `write_all`; no BufWriter, no per-line `println!`;
//! - line buffers (`Vec<&str>`) are reused across cues with `clear()`, no
//!   per-iteration allocation in the strip loops;
//! - Unicode behavior is frozen into generated tables (src/tables.rs) from
//!   Python 3.14.6 / Unicode 16.0.0, not taken from Rust std, because
//!   Python's `\w`, `\s`, `\d`, `isspace`, `splitlines` and cp1252 sets are
//!   not the same as Rust's (e.g. U+001C-U+001F are Python whitespace but
//!   not Rust whitespace);
//! - lossy UTF-8 decoding replicates CPython's error grouping exactly, which
//!   differs from `String::from_utf8_lossy` for truncated/range-invalid
//!   sequences (measured, fixture-driven).

#![cfg_attr(windows, windows_subsystem = "windows")]

use std::cmp::Ordering;
use std::ffi::OsString;
use std::fmt::Write as _;
use std::fs;
use std::io::Write as _;
use std::path::PathBuf;
use std::process::ExitCode;

mod tables;

// ---------------------------------------------------------------------------
// Windows console attach
// ---------------------------------------------------------------------------

/// GUI-subsystem processes get no console. If stdout/stderr handles are
/// missing (interactive launch from cmd/PowerShell), attach to the parent
/// console and rebind the handles so PASS/FAIL is visible. If the parent
/// redirected our handles (another app capturing output), do nothing.
#[cfg(windows)]
fn setup_console() {
    type Handle = *mut core::ffi::c_void;

    const ATTACH_PARENT_PROCESS: u32 = 0xFFFF_FFFF;
    const STD_OUTPUT_HANDLE: u32 = -11i32 as u32;
    const STD_ERROR_HANDLE: u32 = -12i32 as u32;
    const GENERIC_WRITE: u32 = 0x4000_0000;
    const FILE_SHARE_READ_WRITE: u32 = 1 | 2;
    const OPEN_EXISTING: u32 = 3;

    extern "system" {
        fn AttachConsole(dw_process_id: u32) -> i32;
        fn GetStdHandle(n_std_handle: u32) -> Handle;
        fn SetStdHandle(n_std_handle: u32, h_handle: Handle) -> i32;
        fn CreateFileW(
            lp_file_name: *const u16,
            dw_desired_access: u32,
            dw_share_mode: u32,
            lp_security_attributes: *mut core::ffi::c_void,
            dw_creation_disposition: u32,
            dw_flags_and_attributes: u32,
            h_template_file: Handle,
        ) -> Handle;
    }

    fn valid(h: Handle) -> bool {
        !h.is_null() && h as isize != -1
    }

    // SAFETY: plain Win32 calls, no Rust aliasing involved; handles are only
    // used through the Win32 API and Rust's std (which resolves handles
    // lazily on first stdout/stderr use, after this runs).
    unsafe {
        let out = GetStdHandle(STD_OUTPUT_HANDLE);
        let err = GetStdHandle(STD_ERROR_HANDLE);
        if valid(out) && valid(err) {
            return;
        }
        if AttachConsole(ATTACH_PARENT_PROCESS) == 0 {
            return; // no parent console (Explorer, GUI app): stay silent
        }
        let name: Vec<u16> = "CONOUT$\0".encode_utf16().collect();
        let h = CreateFileW(
            name.as_ptr(),
            GENERIC_WRITE,
            FILE_SHARE_READ_WRITE,
            core::ptr::null_mut(),
            OPEN_EXISTING,
            0,
            core::ptr::null_mut(),
        );
        if valid(h) {
            if !valid(out) {
                SetStdHandle(STD_OUTPUT_HANDLE, h);
            }
            if !valid(err) {
                SetStdHandle(STD_ERROR_HANDLE, h);
            }
        }
    }
}

#[cfg(not(windows))]
fn setup_console() {}

// ---------------------------------------------------------------------------
// Table lookups (see src/tables.rs; generated from the Python oracle)
// ---------------------------------------------------------------------------

fn in_ranges(ranges: &[(u32, u32)], cp: u32) -> bool {
    ranges
        .binary_search_by(|&(start, end)| {
            if cp < start {
                Ordering::Greater
            } else if cp > end {
                Ordering::Less
            } else {
                Ordering::Equal
            }
        })
        .is_ok()
}

/// Python: re `[^\W\d_]` (has letters, any script, plus things like
/// superscripts and Roman numerals; excludes ASCII and Unicode decimal digits).
fn is_letter_cp(cp: u32) -> bool {
    in_ranges(tables::LETTER_RANGES, cp)
}

/// Python: str.isspace() == re `\s` (verified equal at generation time).
fn is_space_cp(cp: u32) -> bool {
    in_ranges(tables::SPACE_RANGES, cp)
}

/// Python: re `\d` digit value for timecode fields; `(cp - start) % 10` because
/// adjacent 0-9 blocks merge into single ranges (e.g. math digits).
fn digit_val(c: char) -> Option<u32> {
    let cp = c as u32;
    tables::DIGIT_RANGES
        .binary_search_by(|&(start, end)| {
            if cp < start {
                Ordering::Greater
            } else if cp > end {
                Ordering::Less
            } else {
                Ordering::Equal
            }
        })
        .ok()
        .map(|i| (cp - tables::DIGIT_RANGES[i].0) % 10)
}

fn has_letter(line: &str) -> bool {
    line.chars().any(|c| is_letter_cp(c as u32))
}

/// Python: `line == "" or line.isspace()`.
fn is_blank(line: &str) -> bool {
    line.chars().all(|c| is_space_cp(c as u32))
}

/// Python: str.strip() with default chars (str.isspace set).
fn py_trim(line: &str) -> &str {
    line.trim_matches(|c: char| is_space_cp(c as u32))
}

/// Python: str.splitlines() breaks on \n \v \f \r \x1c \x1d \x1e \x85 U+2028
/// U+2029, treats \r\n as one break, and never yields a trailing empty line
/// after a final break.
fn py_splitlines(text: &str) -> Vec<&str> {
    fn is_break(c: char) -> bool {
        matches!(
            c,
            '\n' | '\u{0B}'
                | '\u{0C}'
                | '\r'
                | '\u{1C}'
                | '\u{1D}'
                | '\u{1E}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        )
    }
    let mut out: Vec<&str> = Vec::with_capacity(text.bytes().filter(|&b| b == b'\n').count() + 1);
    let mut start = 0usize;
    let mut it = text.char_indices().peekable();
    while let Some((i, c)) = it.next() {
        if is_break(c) {
            out.push(&text[start..i]);
            if c == '\r' {
                if let Some(&(_, '\n')) = it.peek() {
                    it.next();
                }
            }
            start = it.peek().map_or(text.len(), |&(j, _)| j);
        }
    }
    if start < text.len() {
        out.push(&text[start..]);
    }
    out
}

// ---------------------------------------------------------------------------
// Decoding: utf-8-sig -> cp1252 -> utf-8 with Python's 'replace' semantics
// ---------------------------------------------------------------------------

const REPLACEMENT: char = '\u{FFFD}';
const CP1252_UNDEFINED: u32 = 0x11_0000;

fn decode_input(data: &[u8]) -> String {
    // 1) utf-8-sig: optional BOM, strict UTF-8.
    let body = data.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(data);
    if let Ok(s) = std::str::from_utf8(body) {
        return s.to_string();
    }
    // 2) cp1252, strict: fails on the five undefined bytes (0x81 0x8D 0x8F
    //    0x90 0x9D). The BOM bytes are mojibake here, exactly as in Python.
    if !data
        .iter()
        .any(|&b| tables::CP1252_MAP[b as usize] == CP1252_UNDEFINED)
    {
        let mut s = String::with_capacity(data.len() + data.len() / 8);
        for &b in data {
            s.push(char::from_u32(tables::CP1252_MAP[b as usize]).unwrap_or(REPLACEMENT));
        }
        return s;
    }
    // 3) utf-8 with errors='replace' (BOM preserved as U+FEFF, as in Python).
    python_lossy_utf8(data)
}

/// CPython's UTF-8 decode with the 'replace' error handler: one U+FFFD per
/// error event, where the event length depends on the failure kind. Mirrors
/// Objects/stringlib/codecs.h (utf8_decode) + unicode_decode_utf8_impl:
///   invalid start byte            -> 1 byte
///   invalid 1st continuation      -> 1 byte
///   invalid 2nd continuation      -> 2 bytes
///   invalid 3rd continuation      -> 3 bytes
///   truncated at end of data      -> all remaining bytes of the sequence
fn python_lossy_utf8(data: &[u8]) -> String {
    let end = data.len();
    let mut out = String::with_capacity(end + end / 8);
    let mut s = 0usize;
    while s < end {
        let b0 = data[s];
        // ASCII fast path: copy runs in one go (CPython does the same).
        if b0 < 0x80 {
            let run = data[s..].iter().position(|&b| b >= 0x80).unwrap_or(end - s);
            if let Ok(t) = std::str::from_utf8(&data[s..s + run]) {
                out.push_str(t);
            }
            s += run;
            continue;
        }
        let cont = |b: u8| (0x80..0xC0).contains(&b);
        if b0 < 0xC2 {
            // 0x80-0xBF lone continuation, 0xC0/0xC1 overlong: 1 byte.
            out.push(REPLACEMENT);
            s += 1;
        } else if b0 < 0xE0 {
            if end - s < 2 {
                out.push(REPLACEMENT);
                s = end;
            } else if !cont(data[s + 1]) {
                out.push(REPLACEMENT);
                s += 1;
            } else {
                let cp = ((b0 as u32 & 0x1F) << 6) | (data[s + 1] as u32 & 0x3F);
                out.push(char::from_u32(cp).unwrap_or(REPLACEMENT));
                s += 2;
            }
        } else if b0 < 0xF0 {
            if end - s < 2 {
                out.push(REPLACEMENT);
                s = end;
            } else {
                let b1 = data[s + 1];
                if !cont(b1) || (b1 < 0xA0 && b0 == 0xE0) || (b0 == 0xED && b1 >= 0xA0) {
                    out.push(REPLACEMENT);
                    s += 1;
                } else if end - s < 3 {
                    out.push(REPLACEMENT);
                    s = end;
                } else if !cont(data[s + 2]) {
                    out.push(REPLACEMENT);
                    s += 2;
                } else {
                    let cp = ((b0 as u32 & 0x0F) << 12)
                        | ((b1 as u32 & 0x3F) << 6)
                        | (data[s + 2] as u32 & 0x3F);
                    out.push(char::from_u32(cp).unwrap_or(REPLACEMENT));
                    s += 3;
                }
            }
        } else if b0 < 0xF5 {
            if end - s < 2 {
                out.push(REPLACEMENT);
                s = end;
            } else {
                let b1 = data[s + 1];
                if !cont(b1) || (b1 < 0x90 && b0 == 0xF0) || (b0 == 0xF4 && b1 >= 0x90) {
                    out.push(REPLACEMENT);
                    s += 1;
                } else if end - s < 3 {
                    out.push(REPLACEMENT);
                    s = end;
                } else if !cont(data[s + 2]) {
                    out.push(REPLACEMENT);
                    s += 2;
                } else if end - s < 4 {
                    out.push(REPLACEMENT);
                    s = end;
                } else if !cont(data[s + 3]) {
                    out.push(REPLACEMENT);
                    s += 3;
                } else {
                    let cp = ((b0 as u32 & 0x07) << 18)
                        | ((b1 as u32 & 0x3F) << 12)
                        | ((data[s + 2] as u32 & 0x3F) << 6)
                        | (data[s + 3] as u32 & 0x3F);
                    out.push(char::from_u32(cp).unwrap_or(REPLACEMENT));
                    s += 4;
                }
            }
        } else {
            // 0xF5-0xFF: invalid start byte.
            out.push(REPLACEMENT);
            s += 1;
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Timecode scanner: re `(\d{1,2}):(\d{2}):(\d{2})[,.]\d{3}\s*-->`
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
struct Tc<'a> {
    hh: u32,
    mm: &'a str,
    ss: &'a str,
}

struct Cur<'a> {
    s: &'a str,
    pos: usize,
}

impl<'a> Cur<'a> {
    fn peek(&self) -> Option<char> {
        self.s[self.pos..].chars().next()
    }
    fn bump(&mut self) -> Option<char> {
        let c = self.peek()?;
        self.pos += c.len_utf8();
        Some(c)
    }
}

fn try_timecode_at(line: &str, i: usize, two_digit_hh: bool) -> Option<Tc<'_>> {
    let mut cur = Cur { s: line, pos: i };
    let c1 = cur.bump()?;
    let d1 = digit_val(c1)?;
    let mut hh = d1;
    if two_digit_hh {
        let c2 = cur.peek()?;
        let d2 = digit_val(c2)?;
        if d2 > 9 {
            return None; // unreachable, digit_val yields 0..=9
        }
        cur.bump();
        hh = d1 * 10 + d2;
    }
    if cur.bump()? != ':' {
        return None;
    }
    let mm_start = cur.pos;
    for _ in 0..2 {
        let d = digit_val(cur.bump()?)?;
        let _ = d;
    }
    let mm = &line[mm_start..cur.pos];
    if cur.bump()? != ':' {
        return None;
    }
    let ss_start = cur.pos;
    for _ in 0..2 {
        let d = digit_val(cur.bump()?)?;
        let _ = d;
    }
    let ss = &line[ss_start..cur.pos];
    match cur.bump()? {
        ',' | '.' => {}
        _ => return None,
    }
    for _ in 0..3 {
        let d = digit_val(cur.bump()?)?;
        let _ = d;
    }
    while let Some(c) = cur.peek() {
        if is_space_cp(c as u32) {
            cur.bump();
        } else {
            break;
        }
    }
    for want in ['-', '-', '>'] {
        if cur.bump()? != want {
            return None;
        }
    }
    Some(Tc { hh, mm, ss })
}

/// Leftmost match, greedy `\d{1,2}` with backtracking to one digit, exactly as
/// Python's re.search would return it.
fn find_timecode(line: &str) -> Option<Tc<'_>> {
    for (i, c) in line.char_indices() {
        if digit_val(c).is_some() {
            if let Some(tc) = try_timecode_at(line, i, true) {
                return Some(tc);
            }
            if let Some(tc) = try_timecode_at(line, i, false) {
                return Some(tc);
            }
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Output construction (paras lists of strip_srt.py, built into one buffer)
// ---------------------------------------------------------------------------

struct Out<'e> {
    buf: String,
    /// Join separator between items: eol normally, eol+eol in keep-timecodes
    /// mode (strip_srt.py line 183: blank line between paragraphs).
    sep: &'e str,
    items: usize,
}

impl<'e> Out<'e> {
    fn new(sep: &'e str, cap: usize) -> Self {
        Out {
            buf: String::with_capacity(cap),
            sep,
            items: 0,
        }
    }
    fn sep(&mut self) {
        if self.items > 0 {
            self.buf.push_str(self.sep);
        }
    }
    /// An empty item ("" in paras): it only contributes its separator.
    fn blank(&mut self) {
        self.sep();
        self.items += 1;
    }
    fn text(&mut self, s: &str) {
        self.sep();
        self.buf.push_str(s);
        self.items += 1;
    }
    fn text_prefixed(&mut self, n: usize, s: &str) {
        self.sep();
        let _ = write!(self.buf, "{:05} {}", n, s);
        self.items += 1;
    }
    fn num_line(&mut self, n: usize) {
        self.sep();
        let _ = write!(self.buf, "{:05}", n);
        self.items += 1;
    }
    fn para(&mut self, number: Option<usize>, tc: Option<Tc<'_>>, parts: &[&str]) {
        self.sep();
        if let Some(n) = number {
            let _ = write!(self.buf, "{:05} ", n);
        }
        if let Some(t) = tc {
            let _ = write!(self.buf, "[{:02}:{}:{}] ", t.hh, t.mm, t.ss);
        }
        for (i, p) in parts.iter().enumerate() {
            if i > 0 {
                self.buf.push(' ');
            }
            self.buf.push_str(p);
        }
        self.items += 1;
    }
}

/// strip_srt.py strip_default(): keep letter lines, collapse blank runs to one
/// "" item, insert "" when dropped scaffolding separated two text lines.
/// In numbered mode each text item is prefixed directly (no per-line String).
fn build_default(lines: &[&str], sep: &str, cap: usize, numbered: bool) -> (String, usize) {
    #[derive(PartialEq)]
    enum Last {
        None,
        Blank,
        Text,
    }
    let mut o = Out::new(sep, cap);
    let mut last = Last::None;
    let mut dropped = false;
    let mut pending_blank = false;
    let mut n = 0usize;
    for &line in lines {
        if is_blank(line) {
            if last != Last::Blank {
                pending_blank = true;
                last = Last::Blank;
            }
            dropped = false;
        } else if has_letter(line) {
            if last == Last::Text && dropped {
                pending_blank = true;
            }
            if pending_blank {
                o.blank();
                pending_blank = false;
            }
            if numbered {
                n += 1;
                o.text_prefixed(n, line);
            } else {
                o.text(line);
            }
            last = Last::Text;
            dropped = false;
        } else {
            dropped = true;
        }
    }
    (o.buf, o.items)
}

/// strip_srt.py numbered-only pipeline: reblock the default paras at "" items
/// and put an index line ("00001") above each block. Trailing/leading blank
/// items are dropped by the block logic, matching the Python trim.
fn build_numbered_only(lines: &[&str], sep: &str, cap: usize) -> (String, usize) {
    #[derive(PartialEq)]
    enum Last {
        None,
        Blank,
        Text,
    }
    let mut o = Out::new(sep, cap);
    let mut last = Last::None;
    let mut dropped = false;
    let mut pending_blank = false;
    let mut block = 0usize;
    for &line in lines {
        if is_blank(line) {
            if last != Last::Blank {
                pending_blank = true;
                last = Last::Blank;
            }
            dropped = false;
        } else if has_letter(line) {
            if last == Last::Text && dropped {
                pending_blank = true;
            }
            if block == 0 || pending_blank {
                if pending_blank && o.items > 0 {
                    o.blank();
                }
                block += 1;
                o.num_line(block);
                pending_blank = false;
            }
            o.text(line);
            last = Last::Text;
            dropped = false;
        } else {
            dropped = true;
        }
    }
    (o.buf, o.items)
}

fn flush_plain(o: &mut Out, n: &mut usize, numbered: bool, plain: &mut Vec<&str>) {
    if !plain.is_empty() {
        if numbered {
            *n += 1;
        }
        let number = if numbered { Some(*n) } else { None };
        o.para(number, None, plain);
        plain.clear();
    }
}

fn flush_cue(
    o: &mut Out,
    n: &mut usize,
    numbered: bool,
    stamp: Option<Tc<'_>>,
    cue: &mut Vec<&str>,
) {
    if !cue.is_empty() {
        if numbered {
            *n += 1;
        }
        let number = if numbered { Some(*n) } else { None };
        o.para(number, stamp, cue);
        cue.clear();
    }
}

/// strip_srt.py strip_timecodes(): one "[HH:MM:SS] merged text" para per cue;
/// text outside cues becomes its own para. Buffers are reused via clear().
fn build_timecodes(lines: &[&str], sep: &str, cap: usize, numbered: bool) -> (String, usize) {
    let mut o = Out::new(sep, cap);
    let mut n = 0usize;
    let mut stamp: Option<Tc<'_>> = None;
    let mut cue: Vec<&str> = Vec::new();
    let mut plain: Vec<&str> = Vec::new();
    for &line in lines {
        if let Some(tc) = find_timecode(line) {
            flush_plain(&mut o, &mut n, numbered, &mut plain);
            flush_cue(&mut o, &mut n, numbered, stamp, &mut cue);
            stamp = Some(tc);
        } else if is_blank(line) {
            flush_plain(&mut o, &mut n, numbered, &mut plain);
            flush_cue(&mut o, &mut n, numbered, stamp, &mut cue);
            stamp = None;
        } else if has_letter(line) {
            let t = py_trim(line);
            if stamp.is_none() {
                plain.push(t);
            } else {
                cue.push(t);
            }
        }
    }
    flush_plain(&mut o, &mut n, numbered, &mut plain);
    flush_cue(&mut o, &mut n, numbered, stamp, &mut cue);
    (o.buf, o.items)
}

// ---------------------------------------------------------------------------
// CLI (argparse-compatible subset, messages matched to the Python script)
// ---------------------------------------------------------------------------

const USAGE: &str =
    "usage: srtstripper [-h] [--keep-timecodes] [--numbered | --numbered-only] [--out OUT] input";

fn help_text() -> String {
    format!(
        "{USAGE}

Strip lines without letters; keep blank separators; optional SRT timecodes.

positional arguments:
  input              input file (read only)

options:
  -h, --help         show this help message and exit
  --keep-timecodes   SRT mode: one '[HH:MM:SS] text' paragraph per cue, cue text merged
  --numbered         prefix each kept text line with a 5-digit counter (00001, 00002, ...)
  --numbered-only    number on its own line per text block (SRT look, no timecodes), blank lines kept
  --out OUT          output file (default: name derived from input)
"
    )
}

struct Args {
    input: PathBuf,
    out: Option<PathBuf>,
    keep_timecodes: bool,
    numbered: bool,
    numbered_only: bool,
}

enum Parsed {
    Args(Box<Args>),
    Help,
    Error(String),
}

#[derive(Clone, Copy, PartialEq)]
enum LongOpt {
    Help,
    KeepTc,
    Num,
    NumOnly,
    Out,
}

const LONGS: &[(&str, LongOpt)] = &[
    ("--help", LongOpt::Help),
    ("--keep-timecodes", LongOpt::KeepTc),
    ("--numbered", LongOpt::Num),
    ("--numbered-only", LongOpt::NumOnly),
    ("--out", LongOpt::Out),
];

/// argparse prefix matching: exact match first, then unique prefix;
/// ambiguous prefixes report the candidates.
enum ResolveErr {
    Unknown,
    Ambiguous(String),
}

fn resolve_long(arg: &str) -> Result<LongOpt, ResolveErr> {
    for &(name, opt) in LONGS {
        if name == arg {
            return Ok(opt);
        }
    }
    let cands: Vec<&str> = LONGS
        .iter()
        .filter(|(name, _)| name.starts_with(arg))
        .map(|(name, _)| *name)
        .collect();
    match cands.len() {
        0 => Err(ResolveErr::Unknown),
        1 => LONGS
            .iter()
            .find(|(name, _)| *name == cands[0])
            .map(|&(_, opt)| opt)
            .ok_or(ResolveErr::Unknown),
        _ => Err(ResolveErr::Ambiguous(format!(
            "ambiguous option: {} could match {}",
            arg,
            cands.join(", ")
        ))),
    }
}

fn parse_args(args: impl Iterator<Item = OsString>) -> Parsed {
    let tokens: Vec<OsString> = args.collect();
    let mut input: Option<PathBuf> = None;
    let mut out: Option<PathBuf> = None;
    let mut keep = false;
    let mut num = false;
    let mut num_only = false;
    let mut extras: Vec<String> = Vec::new();
    let mut after_dd = false; // tokens after "--" are positional

    let mut i = 0;
    while i < tokens.len() {
        let arg = &tokens[i];
        i += 1;
        let s = match arg.to_str() {
            Some(s) if !after_dd => s,
            _ => {
                if input.is_none() {
                    input = Some(PathBuf::from(arg));
                } else {
                    extras.push(arg.to_string_lossy().into_owned());
                }
                continue;
            }
        };
        if s == "--" {
            after_dd = true;
            continue;
        }
        if let Some(rest) = s.strip_prefix("--") {
            let (optname, inline_val) = match rest.split_once('=') {
                Some((n, v)) => (n, Some(v)),
                None => (rest, None),
            };
            let full = format!("--{optname}");
            let opt = match resolve_long(&full) {
                Ok(o) => o,
                Err(ResolveErr::Unknown) => {
                    extras.push(s.to_string()); // argparse defers unknowns
                    continue;
                }
                Err(ResolveErr::Ambiguous(msg)) => return Parsed::Error(msg),
            };
            match opt {
                LongOpt::Help => return Parsed::Help,
                LongOpt::KeepTc | LongOpt::Num | LongOpt::NumOnly => {
                    if let Some(v) = inline_val {
                        return Parsed::Error(format!(
                            "argument {full}: ignored explicit argument '{v}'"
                        ));
                    }
                    match opt {
                        LongOpt::KeepTc => keep = true,
                        LongOpt::Num => num = true,
                        _ => num_only = true,
                    }
                    if num && num_only {
                        return Parsed::Error(
                            "argument --numbered-only: not allowed with argument --numbered"
                                .to_string(),
                        );
                    }
                }
                LongOpt::Out => {
                    let val: Option<OsString> = match inline_val {
                        Some(v) => Some(OsString::from(v)),
                        None => match tokens.get(i).and_then(|t| t.to_str()) {
                            Some(next) if next != "-" && next.starts_with('-') => None,
                            Some(_) => {
                                let v = tokens[i].clone();
                                i += 1;
                                Some(v)
                            }
                            None if i < tokens.len() => {
                                let v = tokens[i].clone();
                                i += 1;
                                Some(v)
                            }
                            None => None,
                        },
                    };
                    match val {
                        Some(v) => out = Some(PathBuf::from(v)),
                        None => {
                            return Parsed::Error(
                                "argument --out: expected one argument".to_string(),
                            )
                        }
                    }
                }
            }
            continue;
        }
        if s == "-h" || (s.len() > 2 && s.starts_with("-h")) {
            // argparse consumes short clusters left to right; -h wins.
            return Parsed::Help;
        }
        if s.len() > 1 && s.starts_with('-') {
            extras.push(s.to_string());
            continue;
        }
        // positional (including "-" and non-UTF8 argv)
        if input.is_none() {
            input = Some(PathBuf::from(arg));
        } else {
            extras.push(arg.to_string_lossy().into_owned());
        }
    }

    let Some(input) = input else {
        return Parsed::Error("the following arguments are required: input".to_string());
    };
    if !extras.is_empty() {
        return Parsed::Error(format!("unrecognized arguments: {}", extras.join(" ")));
    }
    Parsed::Args(Box::new(Args {
        input,
        out,
        keep_timecodes: keep,
        numbered: num,
        numbered_only: num_only,
    }))
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

fn print_out(msg: &str) {
    let mut h = std::io::stdout().lock();
    let _ = writeln!(h, "{msg}");
}

fn print_err(msg: &str) {
    let mut h = std::io::stderr().lock();
    let _ = writeln!(h, "{msg}");
}

/// Python Path() strips trailing separators; do the same so
/// "file.srt/" and "file.srt" behave identically (drive roots are kept).
fn normalize_path(p: PathBuf) -> PathBuf {
    let s = p.to_string_lossy();
    let mut t: &str = &s;
    while t.len() > 1 && (t.ends_with('/') || t.ends_with('\\')) {
        let trimmed = &t[..t.len() - 1];
        if trimmed.ends_with(':') {
            break;
        }
        t = trimmed;
    }
    PathBuf::from(t)
}

/// Python pathlib stem (os.path.splitext on the file name): strip the last
/// dot suffix unless every character before it is a dot.
fn python_stem(name: &str) -> &str {
    if let Some(dot) = name.rfind('.') {
        if name[..dot].bytes().any(|b| b != b'.') {
            return &name[..dot];
        }
    }
    name
}

fn run(args: &Args) -> u8 {
    let input = &args.input;
    if !input.is_file() {
        print_err(&format!("FAIL: input not found: {}", input.display()));
        return 2;
    }
    let data = match fs::read(input) {
        Ok(d) => d,
        Err(e) => {
            print_err(&format!("FAIL: cannot read {}: {e}", input.display()));
            return 1;
        }
    };
    let text = decode_input(&data);
    let eol = if text.contains("\r\n") { "\r\n" } else { "\n" };
    let lines = py_splitlines(&text);
    // One output buffer, sized from the input; the strip loops never allocate
    // per line (Python's join did one big allocation too).
    let cap = text.len() + text.len() / 8 + 64;

    let (body, items, mode, suffix) = if args.keep_timecodes {
        // strip_srt.py: sep = (eol + eol) if keep_timecodes else eol
        let sep = if eol == "\r\n" { "\r\n\r\n" } else { "\n\n" };
        let (b, n) = build_timecodes(&lines, sep, cap, args.numbered);
        let mode = if args.numbered {
            "keep-timecodes+numbered"
        } else {
            "keep-timecodes"
        };
        let suffix = if args.numbered {
            " - timecodes numbered"
        } else {
            " - timecodes"
        };
        (b, n, mode, suffix.to_string())
    } else if args.numbered_only {
        let (b, n) = build_numbered_only(&lines, eol, cap);
        (b, n, "numbered-only", " - numbered".to_string())
    } else {
        let (b, n) = build_default(&lines, eol, cap, args.numbered);
        let mode = if args.numbered {
            "default+numbered"
        } else {
            "default"
        };
        let suffix = if args.numbered {
            " - alpha numbered"
        } else {
            " - alpha"
        };
        (b, n, mode, suffix.to_string())
    };

    let out_path: PathBuf = match &args.out {
        Some(o) => o.clone(),
        None => {
            let name = input
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            let stem = python_stem(&name);
            input.with_file_name(format!("{stem}{suffix}.txt"))
        }
    };

    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            if let Err(e) = fs::create_dir_all(parent) {
                print_err(&format!(
                    "FAIL: cannot create directory {}: {e}",
                    parent.display()
                ));
                return 1;
            }
        }
    }
    let mut file = match fs::File::create(&out_path) {
        Ok(f) => f,
        Err(e) => {
            print_err(&format!("FAIL: cannot write {}: {e}", out_path.display()));
            return 1;
        }
    };
    // Single write of the fully built buffer (one syscall path, like
    // CPython's buffered join+write); no BufWriter needed and no flush
    // semantics to lose. File::create truncates even for empty output,
    // matching Python's open(w) behavior.
    let mut bytes = body;
    if items > 0 {
        bytes.push_str(eol);
    }
    if let Err(e) = file.write_all(bytes.as_bytes()) {
        print_err(&format!("FAIL: cannot write {}: {e}", out_path.display()));
        return 1;
    }

    print_out(&format!(
        "PASS: mode={mode}, wrote {items} lines from {} input lines -> {}",
        lines.len(),
        out_path.display()
    ));
    0
}

fn main() -> ExitCode {
    setup_console();
    match parse_args(std::env::args_os().skip(1)) {
        Parsed::Help => {
            print_out(&help_text());
            ExitCode::SUCCESS
        }
        Parsed::Error(msg) => {
            print_err(&format!("{USAGE}\nsrtstripper: error: {msg}"));
            ExitCode::from(2)
        }
        Parsed::Args(args) => {
            if args.numbered_only && args.keep_timecodes {
                print_err(concat!(
                    "srtstripper: error: --numbered-only writes number lines and no ",
                    "timecodes; drop --keep-timecodes"
                ));
                return ExitCode::from(2);
            }
            let mut args = *args;
            args.input = normalize_path(args.input);
            args.out = args.out.map(normalize_path);
            let code = run(&args);
            ExitCode::from(code)
        }
    }
}

// ---------------------------------------------------------------------------
// Tests (fixtures generated by tools/gen_tables.py from the Python oracle)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    mod splitlines_data {
        include!("testdata/splitlines_cases.rs");
    }
    mod trim_data {
        include!("testdata/trim_cases.rs");
    }
    mod blank_data {
        include!("testdata/blank_cases.rs");
    }
    mod decode_data {
        include!("testdata/decode_cases.rs");
    }
    mod stem_data {
        include!("testdata/stem_cases.rs");
    }

    #[test]
    fn tables_are_sorted_and_disjoint() {
        for t in [
            tables::LETTER_RANGES,
            tables::DIGIT_RANGES,
            tables::SPACE_RANGES,
        ] {
            for w in t.windows(2) {
                assert!(w[0].0 <= w[0].1 && w[0].1 < w[1].0, "table order");
            }
        }
    }

    #[test]
    fn splitlines_matches_python() {
        for (input, expected) in splitlines_data::CASES {
            assert_eq!(
                py_splitlines(input).as_slice(),
                *expected,
                "input {input:?}"
            );
        }
    }

    #[test]
    fn trim_matches_python() {
        for (input, expected) in trim_data::TRIM_CASES {
            assert_eq!(py_trim(input), *expected, "input {input:?}");
        }
    }

    #[test]
    fn blank_matches_python() {
        for (input, expected) in blank_data::BLANK_CASES {
            assert_eq!(is_blank(input), *expected, "input {input:?}");
        }
    }

    #[test]
    fn decode_matches_python() {
        for (data, expected) in decode_data::DECODE_CASES {
            assert_eq!(decode_input(data), *expected, "bytes {data:?}");
        }
    }

    #[test]
    fn stem_matches_python() {
        for (name, expected) in stem_data::STEM_CASES {
            assert_eq!(python_stem(name), *expected, "name {name:?}");
        }
    }

    #[test]
    fn has_letter_matches_python_regex() {
        let sample = include_str!("testdata/letter_sample.tsv");
        for row in sample.lines() {
            let (cp_s, want_s) = row.split_once('\t').expect("tsv row");
            let cp: u32 = cp_s.parse().expect("codepoint");
            let want = want_s == "1";
            let got = char::from_u32(cp).is_some_and(|c| is_letter_cp(c as u32));
            assert_eq!(got, want, "codepoint U+{cp:04X}");
        }
    }

    #[test]
    fn timecode_matches_python_regex() {
        let lines = include_str!("testdata/timecode_lines.txt");
        let expected = include_str!("testdata/timecode_expected.txt");
        for (line, want) in lines.lines().zip(expected.lines()) {
            let got = find_timecode(line)
                .map(|t| format!("{:02}:{}:{}", t.hh, t.mm, t.ss))
                .unwrap_or_else(|| "NONE".to_string());
            assert_eq!(got, want, "line {line:?}");
        }
    }

    #[test]
    fn digit_values() {
        assert_eq!(digit_val('5'), Some(5));
        assert_eq!(digit_val('\u{0663}'), Some(3)); // Arabic-Indic three
        assert_eq!(digit_val('\u{096F}'), Some(9)); // Devanagari nine
        assert_eq!(digit_val('\u{1D7CE}'), Some(0)); // math bold zero
        assert_eq!(digit_val('a'), None);
        assert_eq!(digit_val('\u{00B2}'), None); // superscript two is not \d
    }
}
