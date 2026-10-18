// GENERATED FILE - do not edit by hand (tools/gen_tables.py).
#[rustfmt::skip]
pub const TRIM_CASES: &[(&str, &str)] = &[
    ("", ""),
    (" x ", "x"),
    ("\u{9}\u{A0}x\u{1F} ", "x"),
    ("\u{3000}x\u{3000}", "x"),
    ("xy", "xy"),
    ("\u{85}x", "x"),
    (" x", "x"),
    ("x ", "x"),
    ("\u{2000}\u{2001}z\u{200A}", "z"),
    ("..x..", "..x.."),
    ("\u{1680}y\u{202F}", "y"),
];
