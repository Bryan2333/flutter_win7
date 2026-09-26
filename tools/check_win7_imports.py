#!/usr/bin/env python3
"""Fail if a PE file still imports APIs that are missing on an older Windows.

The API database comes from YY-Thunks' YY.Depends.Analyzer
(src/YY.Depends.Analyzer/Config/<arch>/<os>.txt), which lists every export of
every system DLL of that OS version.

    python tools/check_win7_imports.py flutter_windows.dll \
        --db YY-Thunks/src/YY.Depends.Analyzer/Config --arch x64 --os 6.1.7600

Exit code 0 => nothing missing (the binary can load on that OS).
Exit code 1 => the listed imports would make LoadLibrary fail on that OS.
"""

import argparse
import struct
import sys
from collections import defaultdict

OK = 0
NOT_OK = 1


def read_imports(path):
    """Return {dll_name_lower: [function_name_lower, ...]} of a PE file."""
    data = open(path, "rb").read()
    if data[:2] != b"MZ":
        raise ValueError("%s is not a PE file" % path)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("%s is not a PE file" % path)
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    is64 = struct.unpack_from("<H", data, opt)[0] == 0x20B
    dirs = opt + (112 if is64 else 96)
    imp_rva, _ = struct.unpack_from("<II", data, dirs + 8)  # data dir #1

    sections = []
    sec = opt + opt_size
    for i in range(nsec):
        off = sec + i * 40
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, off + 8)
        sections.append((vaddr, max(vsize, rawsize), rawptr))

    def rva2off(rva):
        for vaddr, size, rawptr in sections:
            if vaddr <= rva < vaddr + size:
                return rawptr + (rva - vaddr)
        raise ValueError("RVA 0x%x is not mapped to a section" % rva)

    def cstr(off):
        return data[off:data.index(b"\0", off)].decode("ascii", "replace")

    ptr = 8 if is64 else 4
    fmt = "<Q" if is64 else "<I"
    ordinal_flag = 1 << (63 if is64 else 31)

    imports = defaultdict(list)
    desc = rva2off(imp_rva)
    while True:
        oft, _ts, _fc, name_rva, ft = struct.unpack_from("<IIIII", data, desc)
        if not (oft or name_rva or ft):
            break
        dll = cstr(rva2off(name_rva)).lower()
        thunk = rva2off(oft or ft)
        while True:
            entry = struct.unpack_from(fmt, data, thunk)[0]
            if entry == 0:
                break
            if entry & ordinal_flag:
                imports[dll].append("ordinal:%d" % (entry & 0xFFFF))
            else:
                imports[dll].append(cstr(rva2off(entry) + 2).lower())
            thunk += ptr
        desc += 20
    return imports


def read_db(path):
    """Return ({dll: {name}}, {dll: {ordinal: name}}) of an analyzer dump."""
    db = {}
    ordinals = {}
    current = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].lower()
            db[current] = set()
            ordinals[current] = {}
        elif current and "=" in line and not line.startswith(";"):
            number, name = line.split("=", 1)
            name = name.strip().lower()
            db[current].add(name)
            if number.strip().isdigit():
                ordinals[current][int(number)] = name
    # Guard against a silently empty/mis-parsed database, which would turn this
    # whole check into a no-op that always passes.
    assert len(db) > 500, "API database looks broken (%d DLLs)" % len(db)
    assert "createfilew" in db["kernel32.dll"], "API database looks broken"
    if "waitonaddress" in db.get("kernel32.dll", ()) | db.get(
            "api-ms-win-core-synch-l1-2-0.dll", set()):
        raise ValueError("%s is not an older-Windows database" % path)
    return db, ordinals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    parser.add_argument("--db", required=True, help="YY.Depends.Analyzer Config dir")
    parser.add_argument("--arch", default="x64")
    parser.add_argument("--os", dest="os_version", default="6.1.7600")
    args = parser.parse_args()

    db_path = "%s/%s/%s.txt" % (args.db, args.arch, args.os_version)
    db, ordinals = read_db(db_path)
    imports = read_imports(args.binary)

    missing_dlls = sorted(d for d in imports if d not in db)
    missing_functions = {}
    for dll, funcs in imports.items():
        if dll not in db:
            continue
        # Ordinal imports (ws2_32.dll and oleaut32.dll use them) are resolved
        # through the database's ordinal table before the name comparison.
        names = [ordinals[dll].get(int(f.split(":")[1]), f) if f.startswith("ordinal:") else f
                 for f in funcs]
        missing = sorted(set(names) - db[dll])
        if missing:
            missing_functions[dll] = missing

    total = sum(len(imports[d]) for d in missing_dlls) + sum(
        len(f) for f in missing_functions.values())
    print("%s: %d imported functions, %d missing on %s/%s"
          % (args.binary, sum(len(v) for v in imports.values()), total,
             args.arch, args.os_version))
    for dll in missing_dlls:
        print("  %-32s (DLL absent on target OS): %s"
              % (dll, " ".join(sorted(imports[dll]))))
    for dll, funcs in sorted(missing_functions.items()):
        print("  %-32s %s" % (dll, " ".join(funcs)))
    if total:
        print("FAIL: this binary cannot be loaded on the target OS.")
        return NOT_OK
    print("OK: every imported API exists on the target OS.")
    return OK


if __name__ == "__main__":
    sys.exit(main())
