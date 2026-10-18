// Compiles the Windows version resource (Properties dialog metadata) into the
// binary. No-op on non-Windows targets; on Windows it uses windres (GNU) or
// rc.exe (MSVC). Keep FILEVERSION/PRODUCTVERSION in srtstripper.rc in sync
// with [package] version.
fn main() {
    println!("cargo:rerun-if-changed=srtstripper.rc");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        embed_resource::compile("srtstripper.rc", embed_resource::NONE);
    }
}
