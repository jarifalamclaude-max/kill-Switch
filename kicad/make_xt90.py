"""Write the AMASS XT90PW-M / XT90PW-F footprints (KiCad 7 format, readable by KiCad 7, 8, 9, 10) into ks.pretty and
a simple VRML 3D model of each into 3dmodels/. Pad layout from the KiCad 10 library footprint
AMASS_XT90PW-M_1x02_P10.90mm_Horizontal (pin 1 = minus, pin 2 = plus, 10.9 mm apart, 3.8 mm holes); the female
is its mirror image, like the XT60PW-F / XT60PW-M pair in the KiCad library.   python3 make_xt90.py"""
import math, os
HERE = os.path.dirname(os.path.abspath(__file__))

def footprint(name, s, descr):
    """s = +1 male (plus pin at +x), -1 female (mirror)."""
    X = lambda x: round(s * x, 4)
    def line(x0, y0, x1, y1, layer, w):
        return f'  (fp_line (start {X(x0)} {y0}) (end {X(x1)} {y1}) (stroke (width {w}) (type solid)) (layer "{layer}"))'
    L = [f'(footprint "{name}" (version 20221018) (generator pcbnew)', '  (layer "F.Cu")',
         f'  (descr "{descr}")', '  (tags "RC XT90 battery")', '  (attr through_hole)',
         f'  (fp_text reference "REF**" (at {X(5.45)} -17.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
         f'  (fp_text value "{name}" (at {X(5.45)} 4.2) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
         f'  (fp_text user "-" (at {X(-4.3)} 2.5) (layer "F.SilkS") (effects (font (size 1.5 1.5) (thickness 0.25))))',
         f'  (fp_text user "+" (at {X(14.7)} 2.5) (layer "F.SilkS") (effects (font (size 1.5 1.5) (thickness 0.25))))',
         f'  (fp_text user "${{REFERENCE}}" (at {X(5.45)} -8.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
         line(-5, -24.65, -5, -1.52, "F.SilkS", 0.12), line(15.9, -24.65, 15.9, -1.52, "F.SilkS", 0.12),
         line(-5, -24.65, 15.9, -24.65, "F.SilkS", 0.12), line(3.7, 2.6, 7.9, 2.6, "F.SilkS", 0.12),
         line(-4.95, -24.6, -4.95, -1.59, "F.Fab", 0.1), line(15.85, -24.6, 15.85, -1.59, "F.Fab", 0.1),
         line(-4.95, -24.6, 15.85, -24.6, "F.Fab", 0.1), line(-0.85, 2.51, 11.75, 2.51, "F.Fab", 0.1),
         line(-4.95, -1.59, -0.85, 2.51, "F.Fab", 0.1), line(15.85, -1.59, 11.75, 2.51, "F.Fab", 0.1),
         line(-5.45, -25.1, 16.35, -25.1, "F.CrtYd", 0.05), line(16.35, -25.1, 16.35, 4.1, "F.CrtYd", 0.05),
         line(16.35, 4.1, -5.45, 4.1, "F.CrtYd", 0.05), line(-5.45, 4.1, -5.45, -25.1, "F.CrtYd", 0.05),
         '  (pad "1" thru_hole roundrect (at 0 0) (size 7.2 7.2) (drill 3.8) (layers "*.Cu" "*.Mask") (roundrect_rratio 0.15))',
         f'  (pad "2" thru_hole circle (at {X(10.9)} 0) (size 7.2 7.2) (drill 3.8) (layers "*.Cu" "*.Mask"))',
         f'  (pad "MP" thru_hole rect (at {X(-4)} -9.4) (size 1.6 2.4) (drill oval 0.6 1.4) (layers "*.Cu" "*.Mask"))',
         f'  (pad "MP" thru_hole rect (at {X(14.9)} -9.4) (size 1.6 2.4) (drill oval 0.6 1.4) (layers "*.Cu" "*.Mask"))',
         f'  (model "${{KIPRJMOD}}/3dmodels/{name}.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))', ")"]
    open(os.path.join(HERE, "ks.pretty", name + ".kicad_mod"), "w").write("\n".join(L) + "\n")

# ------------------------------------------------------------------ VRML (KiCad: 1 unit = 2.54 mm, model y = -footprint y)
def wrl(name, s):
    shapes = []
    def add(pts, faces, rgb, spec=0.2):
        P = ", ".join(f"{s * x / 2.54:.4f} {-y / 2.54:.4f} {z / 2.54:.4f}" for x, y, z in pts)
        F = ", ".join(" ".join(str(i) for i in f) + " -1" for f in faces)
        shapes.append(f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {rgb[0]} {rgb[1]} {rgb[2]} "
                      f"specularColor {spec} {spec} {spec} shininess 0.3 }} }} geometry IndexedFaceSet {{ solid FALSE "
                      f"coord Coordinate {{ point [ {P} ] }} coordIndex [ {F} ] }} }}")
    def box(x0, y0, z0, x1, y1, z1, rgb):
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        add(p, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], rgb)
    def cyl(c, axis, r, a, b, rgb, n=20, spec=0.6):
        p = []
        for k in range(n):
            t = 2 * math.pi * k / n; u, v = r * math.cos(t), r * math.sin(t)
            for h in (a, b):
                q = {"y": (c[0] + u, h, c[1] + v), "z": (c[0] + u, c[1] + v, h)}[axis]; p.append(q)
        faces = [(2 * k, 2 * ((k + 1) % n), 2 * ((k + 1) % n) + 1, 2 * k + 1) for k in range(n)]
        faces += [tuple(2 * k for k in range(n)), tuple(2 * k + 1 for k in reversed(range(n)))]
        add(p, faces, rgb, spec)
    YEL, GOLD, BLK = (0.93, 0.72, 0.08), (0.86, 0.68, 0.25), (0.06, 0.06, 0.06)
    box(-4.95, -24.6, 0.3, 15.85, 2.5, 11.8, YEL)                       # housing lying on the board
    for x in (0.0, 10.9):
        cyl((x, 6.05), "y", 3.4, -24.95, -24.55, BLK)                     # opening in the front face
        cyl((x, 6.05), "y", 2.25 if s > 0 else 2.9, -25.1, -14.0, GOLD)   # contact: 4.5 mm pin (male) / socket (female)
        cyl((x, 0.0), "z", 1.9, -3.4, 0.4, GOLD)                          # solder tail through the board
    open(os.path.join(HERE, "3dmodels", name + ".wrl"), "w").write("#VRML V2.0 utf8\n" + "\n".join(shapes) + "\n")

def ptc_wrl():
    """Radial PTC (Bourns MF-RHT050 / Littelfuse RXEF050 size): 7.4 x 3 x 11 mm disc on two leads; KiCad has no 3D model."""
    shapes = []
    def add(pts, faces, rgb):
        P = ", ".join(f"{x / 2.54:.4f} {-y / 2.54:.4f} {z / 2.54:.4f}" for x, y, z in pts)
        F = ", ".join(" ".join(str(i) for i in f) + " -1" for f in faces)
        shapes.append(f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {rgb[0]} {rgb[1]} {rgb[2]} specularColor 0.3 0.3 0.3 shininess 0.3 }} }} "
                      f"geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [ {P} ] }} coordIndex [ {F} ] }} }}")
    def box(x0, y0, z0, x1, y1, z1, rgb):
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        add(p, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], rgb)
    box(-1.15, -0.9, 3.0, 6.25, 2.1, 14.0, (0.95, 0.62, 0.12))          # disc
    for (x, y) in ((0.0, 0.0), (5.1, 1.2)):
        box(x - 0.3, y - 0.3, -1.5, x + 0.3, y + 0.3, 3.2, (0.75, 0.75, 0.75))   # leads
    open(os.path.join(HERE, "3dmodels", "Fuse_Bourns_MF-RHT050.wrl"), "w").write("#VRML V2.0 utf8\n" + "\n".join(shapes) + "\n")

ptc_wrl()
for name, s, d in (("AMASS_XT90PW-M_1x02_P10.90mm_Horizontal", 1, "XT90 horizontal PCB male (battery side), 45 A rated / 90 A peak"),
                   ("AMASS_XT90PW-F_1x02_P10.90mm_Horizontal", -1, "XT90 horizontal PCB female (ESC side), mirror of XT90PW-M")):
    footprint(name, s, d); wrl(name, s)
print("XT90 footprints and models written")
