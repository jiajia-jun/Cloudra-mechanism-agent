import copy
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree as E

n = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
with (
    ZipFile(".deck-work/contrast.pptx") as old,
    ZipFile(".deck-work/redraw-slide.pptx") as new,
    ZipFile(".deck-work/redrawn.pptx", "w", ZIP_DEFLATED) as out,
):
    r = E.fromstring(new.read("ppt/slides/slide1.xml"))
    prev = E.fromstring(old.read("ppt/slides/slide5.xml"))
    tree = r.find("p:cSld/p:spTree", n)
    for id, x, y, w, h in [("110", 111, 242, 132, 126), ("109", 390, 266, 205, 101)]:
        pic = copy.deepcopy(
            next(p for p in prev.findall(".//p:pic", n) if p.find("p:nvPicPr/p:cNvPr", n).get("id") == id)
        )
        pic.find("p:nvPicPr/p:cNvPr", n).set("id", str(900 + int(id)))
        xp = pic.find("p:spPr/a:xfrm", n)
        xp.find("a:off", n).attrib.update({"x": str(round(x * 9525)), "y": str(round(y * 9525))})
        xp.find("a:ext", n).attrib.update({"cx": str(round(w * 9525)), "cy": str(round(h * 9525))})
        tree.append(pic)
    for f in old.infolist():
        out.writestr(
            f,
            E.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)
            if f.filename == "ppt/slides/slide5.xml"
            else old.read(f.filename),
        )
