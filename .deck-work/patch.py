import colorsys
import re
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree as E

n = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def recolor(v):
    if not re.fullmatch("[0-9A-Fa-f]{6}", v):
        return v
    r, g, b = [int(v[k : k + 2], 16) / 255 for k in (0, 2, 4)]
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    if v.upper() in ["AF7631", "B17A1C", "A9791B"]:
        return "9C7B00"
    if v.upper() == "E5C692":
        return "F4D54B"
    if v.upper() in ["FBF3E5", "FFF2CC"]:
        return "FFF6CC"
    if s > 0.2 and 0.48 < h < 0.72:
        return "EDF4F0" if lightness > 0.8 else ("D5E2D9" if lightness > 0.68 else ("78A996" if lightness > 0.55 else "155C44"))
    return v


with ZipFile(".deck-work/candidate.pptx") as z, ZipFile(".deck-work/patched.pptx", "w", ZIP_DEFLATED) as out:
    for f in z.infolist():
        data = z.read(f.filename)
        if f.filename.startswith("ppt/") and f.filename.endswith(".xml") and "/notes" not in f.filename:
            root = E.fromstring(data)
            for c in root.findall(".//a:srgbClr", n):
                c.set("val", recolor(c.get("val", "")))
            # Bright brand yellow for existing top strips, process connectors and stage dots.
            for sp in root.findall(".//p:sp", n):
                xp = sp.find("p:spPr/a:xfrm", n)
                if xp is not None:
                    off = xp.find("a:off", n)
                    ext = xp.find("a:ext", n)
                    if (
                        off is not None
                        and ext is not None
                        and int(off.get("y", "0")) < 80000
                        and int(ext.get("cx", "0")) > 12000000
                        and int(ext.get("cy", "0")) < 100000
                    ):
                        fill = sp.find("p:spPr/a:solidFill/a:srgbClr", n)
                        if fill is not None:
                            fill.set("val", "F4D54B")
            for c in root.xpath(".//a:ln/a:solidFill/a:srgbClr", namespaces=n):
                if c.get("val") == "9C7B00":
                    c.set("val", "E8C63D")
            for c in root.xpath(".//p:spPr/a:solidFill/a:srgbClr", namespaces=n):
                if c.get("val") == "9C7B00":
                    c.set("val", "F4D54B")
            # Remove residual WordArt glow/shadows from live text.
            for eff in root.xpath(
                ".//a:rPr/a:effectLst | .//a:defRPr/a:effectLst | .//a:endParaRPr/a:effectLst", namespaces=n
            ):
                eff.getparent().remove(eff)
            # Ensure fonts in theme and inherited text resolve consistently.
            for e in root.xpath(".//a:latin | .//a:ea | .//a:cs", namespaces=n):
                if e.get("typeface") and e.get("typeface") not in ["Arial", "Hiragino Sans GB"]:
                    e.set("typeface", "Hiragino Sans GB")
            data = E.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        out.writestr(f, data)
print("patched")
