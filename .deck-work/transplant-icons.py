import copy
import re
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree as E

n = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
with (
    ZipFile(".deck-work/redrawn.pptx") as old,
    ZipFile(".deck-work/icons.pptx") as new,
    ZipFile(".deck-work/all-redrawn.pptx", "w", ZIP_DEFLATED) as out,
):
    for f in old.infolist():
        data = old.read(f.filename)
        m = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", f.filename)
        if m and int(m.group(1)) in [11, 15, 18]:
            i = int(m.group(1))
            r = E.fromstring(data)
            tree = r.find("p:cSld/p:spTree", n)
            for pic in list(tree.findall("p:pic", n)):
                tree.remove(pic)
            nid = max(int(e.get("id")) for e in r.findall(".//p:cNvPr", n)) + 1
            for j in {11: [1], 15: [2], 18: [3, 4, 5, 6]}[i]:
                nr = E.fromstring(new.read(f"ppt/slides/slide{j}.xml"))
                for sh in nr.findall("p:cSld/p:spTree/p:sp", n):
                    cp = copy.deepcopy(sh)
                    cp.find("p:nvSpPr/p:cNvPr", n).set("id", str(nid))
                    nid += 1
                    tree.append(cp)
            data = E.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)
        out.writestr(f, data)
