"""Make the 3D view work in any KiCad version (7, 8, 9, 10), with or without KiCad's 3D library installed:
every 3D model a board uses is copied into kicad/3dmodels/ (STEP from the official kicad-packages3D repository)
and each footprint gets exactly one model line pointing at ${KIPRJMOD}/3dmodels/<name>.step. KIPRJMOD is the
folder of the opened board, so the models travel with the project folder / zip.
    python3 bundle_3d.py ks_tht.kicad_pcb [ks_smd.kicad_pcb]"""
import os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "3dmodels")
REPO = "https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/{tag}/{lib}.3dshapes/{name}"
TAGS = ("10.0.8", "9.0.9")
RENAME = {}            # footprint model name -> name in the 3D repository, when they differ
CUSTOM = {"Fuse_Bourns_MF-RHT050": "Fuse_Bourns_MF-RHT050.wrl"}   # no library model: drawn by make_xt90.py

def fetch(lib, stem):
    """Download lib.3dshapes/stem.step (or .wrl) once; return the file name in 3dmodels/ or None."""
    for ext in (".step", ".wrl"):
        fn = stem + ext
        if os.path.exists(os.path.join(DIR, fn)): return fn
    for ext in (".step", ".wrl"):
        for tag, name in [(t, n) for t in TAGS for n in dict.fromkeys((RENAME.get(stem, stem), stem.replace("KathodeUp", "CathodeUp")))]:
            fn = name + ext
            out = os.path.join(DIR, stem + ext)
            r = subprocess.run(["curl", "-sS", "-f", "-L", "-o", out, REPO.format(tag=tag, lib=lib, name=fn)], capture_output=True)
            if r.returncode == 0 and os.path.getsize(out) > 1000: return stem + ext
            if os.path.exists(out): os.remove(out)
    return None

MODEL = re.compile(r'\n(?P<ind>[ \t]*)\(model "(?P<path>[^"]+)"(?P<body>.*?)\n(?P=ind)\)', re.S)

STACKUP = """    (stackup
      (layer "F.SilkS" (type "Top Silk Screen") (color "White"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness 0.07))
      (layer "dielectric 1" (type "core") (thickness 1.44) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.07))
      (layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness 0.01))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
      (copper_finish "HAL lead-free")
      (dielectric_constraints no)
    )
"""

def green_stackup(t):
    """Board stackup: green solder mask, white silkscreen, 2 oz (70 um) copper, 1.6 mm. KiCad's 3D viewer takes the
    board colours from here (Preferences > 3D viewer > use board stackup colours, on by default)."""
    if "(stackup" in t: return t
    return t.replace("\n  (setup\n", "\n  (setup\n" + STACKUP, 1)

def bundle(path):
    os.makedirs(DIR, exist_ok=True)
    t = green_stackup(open(path).read())
    # split into top-level footprints so each one keeps a single model
    parts = re.split(r'(?=\n  \(footprint )', t)
    missing, n = set(), 0
    for i, chunk in enumerate(parts):
        if not chunk.startswith("\n  (footprint "): continue
        models = list(MODEL.finditer(chunk))
        if not models: continue
        first = models[0]; p = first.group("path")
        m = re.match(r'\$\{[A-Z0-9_]+\}/(?P<lib>[^/]+)\.3dshapes/(?P<stem>[^/]+)\.(wrl|step|stp)$', p)
        if p.startswith("${KIPRJMOD}/"):
            newp = p
        elif m and m.group("stem") in CUSTOM:
            newp = "${KIPRJMOD}/3dmodels/" + CUSTOM[m.group("stem")]
        elif m:
            fn = fetch(m.group("lib"), m.group("stem"))
            if fn is None: missing.add(p); newp = p
            else: newp = "${KIPRJMOD}/3dmodels/" + fn
        else:
            newp = p
        keep = "\n" + first.group("ind") + f'(model "{newp}"' + first.group("body") + "\n" + first.group("ind") + ")"
        out, last = [], 0
        for k, mm in enumerate(models):
            out.append(chunk[last:mm.start()]); out.append(keep if k == 0 else ""); last = mm.end()
        out.append(chunk[last:])
        parts[i] = "".join(out); n += 1
    open(path, "w").write("".join(parts))
    used = sorted(set(re.findall(r'\$\{KIPRJMOD\}/3dmodels/([^"]+)"', "".join(parts))))
    print(f"{os.path.basename(path)}: {n} footprints with one bundled model, {len(used)} model files"
          + (f", MISSING: {sorted(missing)}" if missing else ""))
    return used, missing

if __name__ == "__main__":
    for p in sys.argv[1:]: bundle(p)
