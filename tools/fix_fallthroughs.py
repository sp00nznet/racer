#!/usr/bin/env python3
"""
fix_fallthroughs.py — repair N64Recomp split-function fallthroughs.

When N64Recomp finds a JAL into the middle of a function, it splits that
function in two. The first part (often named static_0_XXXXXXXX) ends with a
plain instruction and *falls through* into the second part on real hardware —
but the generated C just returns, so the continuation never runs. That leaves
globals uninitialized and the game crashes later (the entire class of Phase 5
crashes: controller parser, framebuffer allocator, ...).

This tool finds every function whose body ends without a return / terminal goto
/ tail call (a genuine fallthrough) and appends an explicit call to the function
at the next address (its continuation), which is exactly what falling through
does. It is idempotent — re-run it after every N64Recomp regeneration.

Usage:  py tools/fix_fallthroughs.py [--dry-run]
"""
import re, glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOMP_DIR = os.path.join(ROOT, "RecompiledFuncs")
VRAM_BASE = 0x80000400
MARKER = "@fallthrough-fix"
PROLOGUE = ("uint64_t hi = 0, lo = 0, result = 0;", "int c1cs = 0;")

def load_stubs():
    stubs = set()
    with open(os.path.join(ROOT, "recomp.toml")) as f:
        for l in f:
            m = re.search(r'"\s*(\w+)\s*"', l)
            if m and "stubs" not in l:
                stubs.add(m.group(1))
    return stubs

def build_addr_map():
    """address -> function name, from the overlay table + name-embedded addrs."""
    addr2name = {}
    inl = os.path.join(RECOMP_DIR, "recomp_overlays.inl")
    if os.path.exists(inl):
        txt = open(inl, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'\.func = (\w+),\s*\.offset = (0x[0-9A-Fa-f]+)', txt):
            addr2name[VRAM_BASE + int(m.group(2), 16)] = m.group(1)
    # add every name that embeds its address (static_0_, func_, libultra_split_, *_8xxxxxxx)
    func_re = re.compile(r'^RECOMP_FUNC\s+void\s+(\w+)\s*\(')
    for fp in glob.glob(os.path.join(RECOMP_DIR, "funcs_*.c")):
        for ln in open(fp, encoding="utf-8", errors="replace"):
            m = func_re.match(ln)
            if not m:
                continue
            name = m.group(1)
            hm = re.search(r'([0-9A-Fa-f]{8})$', name)
            if hm:
                a = int(hm.group(1), 16)
                if 0x80000000 <= a < 0x80800000:
                    addr2name.setdefault(a, name)
    return addr2name

def func_addr(name):
    hm = re.search(r'([0-9A-Fa-f]{8})$', name)
    return int(hm.group(1), 16) if hm else None

def main():
    dry = "--dry-run" in sys.argv
    stubs = load_stubs()
    addr2name = build_addr_map()
    addrs = sorted(addr2name)
    import bisect
    func_re = re.compile(r'^RECOMP_FUNC\s+void\s+(\w+)\s*\(')

    fixed = 0; skipped_noaddr = 0; total_ft = 0
    for fp in glob.glob(os.path.join(RECOMP_DIR, "funcs_*.c")):
        lines = open(fp, encoding="utf-8", errors="replace").read().split("\n")
        out = []
        i = 0; n = len(lines)
        cur = None; body_start = None
        changed = False
        while i < n:
            ln = lines[i]
            m = func_re.match(ln)
            if m:
                cur = m.group(1); body_start = len(out)
                out.append(ln); i += 1; continue
            if cur is not None and ln.strip() == ";}":
                # analyze the just-collected body in `out[body_start+1:]`
                body = out[body_start+1:]
                code = [l.strip() for l in body
                        if l.strip() and not l.strip().startswith("//")]
                real = [l for l in code if l not in PROLOGUE]
                is_ft = False
                if real and cur not in stubs and MARKER not in "\n".join(body):
                    last = real[-1]
                    has_ret = any("return;" in l for l in real)
                    term_goto = last.startswith("goto ")
                    tail_call = bool(re.match(r'\w+\(rdram, ctx\);$', last))
                    is_ft = not has_ret and not term_goto and not tail_call
                if is_ft:
                    total_ft += 1
                    a = func_addr(cur)
                    cont = None
                    if a is not None:
                        j = bisect.bisect_right(addrs, a)
                        if j < len(addrs):
                            cont = addr2name[addrs[j]]
                    if cont and cont != cur:
                        out.append("    // %s: split fallthrough -> chain to continuation" % MARKER)
                        out.append("    %s(rdram, ctx);" % cont)
                        fixed += 1; changed = True
                    else:
                        skipped_noaddr += 1
                out.append(ln); cur = None; body_start = None; i += 1; continue
            out.append(ln); i += 1
        if changed and not dry:
            open(fp, "w", encoding="utf-8").write("\n".join(out))

    print("fallthrough functions found:        %d" % total_ft)
    print("chained to continuation:            %d" % fixed)
    print("skipped (no resolvable continuation):%d" % skipped_noaddr)
    if dry:
        print("(dry run — no files written)")

if __name__ == "__main__":
    main()
