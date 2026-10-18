//! srtstripper - strip non-alphabetic lines from SRT/text files.
//!
//! Rust port of strip_srt.py. Standalone: no runtime dependencies, no
//! external crates. On Windows the exe is built as a GUI-subsystem binary so
//! no console window ever appears when it is launched by another app; when
//! launched from a console it attaches to the parent console to print.

#![cfg_attr(windows, windows_subsystem = "windows")]

fn main() {
    println!("srtstripper {}", env!("CARGO_PKG_VERSION"));
}
