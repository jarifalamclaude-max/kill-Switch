"""Make the 3D models show in KiCad 7, 8 and 9: every footprint model that points at ${KICAD6_3DMODEL_DIR} gets
copies for ${KICAD7_3DMODEL_DIR} (.wrl), ${KICAD8_3DMODEL_DIR} and ${KICAD9_3DMODEL_DIR} (.step). KiCad loads the
ones whose path variable it knows and skips the rest.
Run with any python3 after the board is written:  python3 fix_3d_models.py ks_tht.kicad_pcb [ks_power.kicad_pcb]"""
import re, sys

def fix(path):
    t = open(path).read()
    pat = re.compile(r'(?P<ind>[ \t]*)\(model "\$\{KICAD6_3DMODEL_DIR\}/(?P<file>[^"]+)\.wrl"(?P<body>.*?\n(?P=ind)\))', re.S)
    n = 0
    def rep(m):
        nonlocal n
        n += 1
        ind, f, body = m.group("ind"), m.group("file"), m.group("body")
        out = [m.group(0)]
        for var, ext in (("KICAD7_3DMODEL_DIR", "wrl"), ("KICAD8_3DMODEL_DIR", "step"), ("KICAD9_3DMODEL_DIR", "step")):
            out.append(f'{ind}(model "${{{var}}}/{f}.{ext}"{body}')
        return "\n".join(out)
    if "${KICAD9_3DMODEL_DIR}" in t:
        print(path, "already has the extra model paths"); return
    t = pat.sub(rep, t)
    open(path, "w").write(t)
    print(path, n, "models now have KiCad 7/8/9 paths")

if __name__ == "__main__":
    for p in sys.argv[1:]: fix(p)
