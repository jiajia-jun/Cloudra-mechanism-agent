from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
import re
n={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
A=lambda s:'{'+n['a']+'}'+s
with ZipFile('.deck-work/repaired.pptx') as z,ZipFile('.deck-work/contrast.pptx','w',ZIP_DEFLATED) as out:
 for f in z.infolist():
  data=z.read(f.filename)
  if re.fullmatch(r'ppt/slides/slide\d+\.xml',f.filename):
   r=E.fromstring(data)
   for sp in r.findall('.//p:sp',n):
    txt=''.join(sp.xpath('.//a:t/text()',namespaces=n));pr=sp.find('p:spPr',n)
    if pr is None:continue
    geom=pr.find('a:prstGeom',n)
    if txt and geom is not None and geom.get('prst')=='flowChartTerminator':
     st=sp.find('p:style',n)
     if st is not None:sp.remove(st)
     geom.set('prst','rect')
    if txt in ['新药发现','临床研究','临床前研究','新药申请']:
     for e in list(pr):
      if E.QName(e).localname in ['solidFill','gradFill','noFill','effectLst']:pr.remove(e)
     fi=E.Element(A('solidFill'));E.SubElement(fi,A('srgbClr'),val='155C44' if txt in ['新药发现','临床研究'] else 'F4D54B');pr.insert(2,fi)
     for rp in sp.xpath('.//a:rPr | .//a:defRPr | .//a:endParaRPr',namespaces=n):
      for e in list(rp):
       if E.QName(e).localname in ['solidFill','gradFill','noFill']:rp.remove(e)
      fi=E.Element(A('solidFill'));E.SubElement(fi,A('srgbClr'),val='FFFFFF' if txt in ['新药发现','临床研究'] else '155C44');rp.insert(0,fi)
    # DrawingML fill precedes line; prevents Office from reverting to inherited fill.
    for fi in list(pr):
     if E.QName(fi).localname in ['solidFill','gradFill','noFill','blipFill','pattFill','grpFill']:
      pr.remove(fi); idx=next((k for k,e in enumerate(pr) if E.QName(e).localname in ['ln','effectLst','effectDag','scene3d','sp3d','extLst']),len(pr));pr.insert(idx,fi)
   data=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
  out.writestr(f,data)
