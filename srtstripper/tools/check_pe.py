#!/usr/bin/env python3
"""Print the PE subsystem of a Windows exe (2 = GUI, 3 = console).

Usage: python srtstripper/tools/check_pe.py path\\to\\srtstripper.exe
"""
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()
if data[:2] != b"MZ":
    sys.exit("FAIL: not an exe")
e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
    sys.exit("FAIL: no PE header")
coff = e_lfanew + 4
opt_off = coff + 20
magic = struct.unpack_from("<H", data, opt_off)[0]
if magic == 0x10B:
    subsystem = struct.unpack_from("<H", data, opt_off + 0x46)[0]
elif magic == 0x20B:
    subsystem = struct.unpack_from("<H", data, opt_off + 0x44)[0]
else:
    sys.exit(f"FAIL: unknown optional header magic 0x{magic:X}")
names = {2: "GUI", 3: "console"}
print(f"{path.name}: PE magic 0x{magic:X}, subsystem {subsystem} ({names.get(subsystem, '?')})")
