
import sys, numpy as np
from rdkit import Chem
EL=[None]*21
def readxyz(p):
    L=open(p).read().splitlines()
    n=int(L[0]); 
    els=[]; co=[]
    for l in L[2:2+n]:
        s=l.split(); els.append(s[0]); co.append([float(x) for x in s[1:4]])
    return els, np.array(co)

def dih(p0,p1,p2,p3):
    b0=p0-p1; b1=p2-p1; b2=p3-p2
    b1n=b1/np.linalg.norm(b1)
    v=b0-np.dot(b0,b1n)*b1n; w=b2-np.dot(b2,b1n)*b1n
    return np.degrees(np.arctan2(np.dot(np.cross(b1n,v),w), np.dot(v,w)))

def report(p, bonds):
    els, c = readxyz(p)
    print("### "+p)
    print(" atom table (1-based): "+" ".join("%d=%s"%(i+1,e) for i,e in enumerate(els)))
    P4=np.array([c[0],c[1],c[2],c[5]]); cc=P4.mean(axis=0)
    _,_,Vt=np.linalg.svd(P4-cc); nn=Vt[2]; nn/=np.linalg.norm(nn)
    if np.dot(c[6]-cc,nn)<0: nn=-nn
    print(" alkene plane = best fit of atoms 1,2,3,6 ; sign convention: atom7 (C10 methano) positive")
    for i in [6,17,18,19,20]:
        print("   sdist atom%-2d %s = %+0.4f A"%(i+1, els[i], np.dot(c[i]-cc,nn)))
    print(" key bonds:")
    for (i,j,lab) in bonds:
        print("   %-22s r(%2d,%2d) = %7.4f A"%(lab,i+1,j+1,np.linalg.norm(c[i]-c[j])))
    print(" dihedrals:")
    for (a,b,cc_,d,lab) in [ (17,0,2,6,"Cdip-C1-C3-C10"), (19,1,5,6,"O20-C2-C9-C10"),
                             (18,19,1,0,"N19-O20-C2-C1"), (17,0,1,19,"Cdip-C1-C2-O20"),
                             (20,17,18,19,"H21-Cdip-N19-O20") ]:
        print("   %-20s dih(%2d,%2d,%2d,%2d) = %+8.2f deg"%(lab,a+1,b+1,cc_+1,d+1,dih(c[a],c[b],c[cc_],c[d])))
    print()
for p in sys.argv[1:]:
    report(p, [(0,17,"C1-Cdip form"),(1,19,"C2-O20 form"),(0,1,"C1-C2"),(17,18,"Cdip-N19"),(18,19,"N19-O20"),(17,20,"Cdip-H21")])
