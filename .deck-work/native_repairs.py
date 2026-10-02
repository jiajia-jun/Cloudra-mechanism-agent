import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree as E

n = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def tag(a):
    return "{" + n["a"] + "}" + a


def set_box(sp, x, y, w, h):
    xp = sp.find("p:spPr/a:xfrm", n)
    xp.find("a:off", n).attrib.update({"x": str(round(x * 9525)), "y": str(round(y * 9525))})
    xp.find("a:ext", n).attrib.update({"cx": str(round(w * 9525)), "cy": str(round(h * 9525))})


def set_text(sp, lines, size, color="2D3C32", bold=False, align="left"):
    tx = sp.find("p:txBody", n)
    bp = tx.find("a:bodyPr", n)
    for k in ["lIns", "rIns", "tIns", "bIns"]:
        bp.set(k, "0")
    bp.set("wrap", "square")
    for e in list(bp):
        if E.QName(e).localname in ["spAutoFit", "normAutofit", "noAutofit"]:
            bp.remove(e)
    E.SubElement(bp, tag("noAutofit"))
    for p in tx.findall("a:p", n):
        tx.remove(p)
    for line in lines:
        p = E.SubElement(tx, tag("p"))
        pp = E.SubElement(p, tag("pPr"), algn={"left": "l", "center": "ctr", "right": "r"}[align])
        E.SubElement(pp, tag("buNone"))
        r = E.SubElement(p, tag("r"))
        rp = E.SubElement(r, tag("rPr"), sz=str(round(size * 75)), b="1" if bold else "0")
        fill = E.SubElement(rp, tag("solidFill"))
        E.SubElement(fill, tag("srgbClr"), val=color)
        for f in ["latin", "ea", "cs"]:
            E.SubElement(rp, tag(f), typeface="Hiragino Sans GB")
        E.SubElement(r, tag("t")).text = line


rec = [json.loads(line) for line in open(".deck-work/after.ndjson")]


def key(t):
    return re.sub(r"\s+", "", t)


styles = {(r["slideIndex"], key(r.get("text", ""))): r.get("style", {}) for r in rec if r.get("text")}
with ZipFile(".deck-work/patched.pptx") as z, ZipFile(".deck-work/repaired.pptx", "w", ZIP_DEFLATED) as out:
    for f in z.infolist():
        data = z.read(f.filename)
        m = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", f.filename)
        if m:
            i = int(m.group(1))
            root = E.fromstring(data)
            for sp in root.findall(".//p:sp", n):
                txt = "".join(sp.xpath(".//a:t/text()", namespaces=n))
                st = styles.get((i - 1, key(txt)), {})
                if st.get("fontSize"):
                    sz = str(round(st["fontSize"] * 75))
                    for r in sp.findall(".//a:r", n):
                        rp = r.find("a:rPr", n)
                        if rp is None:
                            rp = E.Element(tag("rPr"))
                            r.insert(0, rp)
                        if not rp.get("sz"):
                            rp.set("sz", sz)
                    for e in sp.findall(".//a:defRPr", n):
                        if not e.get("sz"):
                            e.set("sz", sz)
                geom = sp.find("p:spPr/a:prstGeom", n)
                if geom is not None and geom.get("prst") == "flowChartTerminator":
                    pr = sp.find("p:spPr", n)
                    for e in list(pr):
                        if E.QName(e).localname in ["solidFill", "gradFill", "effectLst"]:
                            pr.remove(e)
                    E.SubElement(pr, tag("noFill"))
                    bp = sp.find("p:txBody/a:bodyPr", n)
                    if bp is not None:
                        for k in ["lIns", "rIns", "tIns", "bIns"]:
                            bp.set(k, "0")
                if i == 1 and txt.startswith("基于智能代理"):
                    set_text(
                        sp, ["基于智能代理的自动化轴手性体系", "药物计算驱动研发系统"], 50, "19362B", True, "center"
                    )
                    set_box(sp, 110, 236, 1060, 182)
                if i == 5:
                    oid = sp.find("p:nvSpPr/p:cNvPr", n).get("id")
                    if oid == "57":
                        set_text(sp, ["COX-2"], 18)
                        set_box(sp, 130, 462, 150, 30)
                    if oid == "65":
                        set_text(sp, ["Drug discovery"], 25, "9C7B00", True, "center")
                        set_box(sp, 175, 563, 345, 38)
                    if oid == "67":
                        set_text(sp, ["Development"], 25, "9C7B00", True, "center")
                        set_box(sp, 727, 563, 345, 38)
                    if oid == "47":
                        set_text(sp, ["总花费: ＄500 million and rising", "总费时: 5-10 Years and falling"], 16)
                        set_box(sp, 160, 605, 530, 55)
            if i == 5:
                for pic in root.findall(".//p:pic", n):
                    xp = pic.find("p:spPr/a:xfrm", n)
                    off = xp.find("a:off", n)
                    ext = xp.find("a:ext", n)
                    x = int(off.get("x"))
                    w = int(ext.get("cx"))
                    if x < 0:
                        off.set("x", "0")
                    if x + w > 12179300:
                        off.set("x", str(12179300 - w))
                tree = root.find("p:cSld/p:spTree", n)
                for cx in list(tree.findall("p:cxnSp", n)):
                    tree.remove(cx)
                    tree.insert(2, cx)
            data = E.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        out.writestr(f, data)
