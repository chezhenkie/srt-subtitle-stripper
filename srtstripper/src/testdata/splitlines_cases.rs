// GENERATED FILE - do not edit by hand (tools/gen_tables.py).
#[rustfmt::skip]
pub const CASES: &[(&str, &[&str])] = &[
    ("", &[]),
    ("\u{A}", &[""]),
    ("\u{A}\u{A}", &["", ""]),
    ("\u{D}\u{A}", &[""]),
    ("\u{D}", &[""]),
    ("a\u{D}\u{A}b", &["a", "b"]),
    ("a\u{D}b", &["a", "b"]),
    ("a\u{D}\u{D}\u{A}b", &["a", "", "b"]),
    ("a\u{A}", &["a"]),
    ("a\u{D}\u{A}\u{D}", &["a", ""]),
    ("a\u{A}b\u{D}c\u{B}d\u{C}e\u{1C}g\u{1D}h\u{1E}i\u{85}j\u{2028}k\u{2029}l", &["a", "b", "c", "d", "e", "g", "h", "i", "j", "k", "l"]),
    ("a\u{B}b", &["a", "b"]),
    ("x\u{85}y", &["x", "y"]),
    ("a\u{2028}", &["a"]),
    ("hello", &["hello"]),
    ("\u{2028}\u{2029}", &["", ""]),
    ("a\u{D}\u{A}\u{D}\u{A}b", &["a", "", "b"]),
    ("\u{D}\u{D}", &["", ""]),
    ("ab\u{2028}cd", &["ab", "cd"]),
    ("\u{1E}", &[""]),
];
