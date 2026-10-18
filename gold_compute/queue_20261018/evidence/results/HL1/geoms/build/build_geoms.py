
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from scipy.optimize import minimize
import os, json

OUT = "/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/geoms/build"
os.makedirs(OUT, exist_ok=True)
np.set_printoptions(precision=4, suppress=True)

nb = Chem.AddHs(Chem.MolFromSmiles("C1=CC2CCC1C2"))
ps = AllChem.ETKDGv3(); ps.randomSeed = 20261018
AllChem.EmbedMolecule(nb, ps)
AllChem.MMFFOptimizeMolecule(nb, maxIters=5000)
X = np.array(nb.GetConformer().GetPositions())

A, B, BH1, BH2, MB = 0, 1, 2, 5, 6
u = (X[B]-X[A]); u /= np.linalg.norm(u)
P4 = np.array([X[A], X[B], X[BH1], X[BH2]])
c = P4.mean(axis=0)
_,_,Vt = np.linalg.svd(P4-c)
n = Vt[2]; n /= np.linalg.norm(n)
if np.dot(X[MB]-c, n) < 0: n = -n

HsOf = {i:[] for i in range(7)}
for a in nb.GetAtoms():
    if a.GetSymbol()=="H":
        HsOf[a.GetNeighbors()[0].GetIdx()].append(a.GetIdx())

parents = [A,B,BH1,3,4,BH2,MB]
work = [("C", p) for p in parents]
for hv in parents:
    for h in HsOf[hv]:
        work.append(("H", h))
assert len(work)==17

def build_ring(lenAB, lenBO, lenON, lenNC, lenCA, targets):
    best=None
    for t1 in np.arange(60, 175, 1.0):
        O2 = np.array([lenAB,0.0]) + lenBO*np.array([np.cos(np.radians(t1)), np.sin(np.radians(t1))])
        for t2 in np.arange(20, 175, 1.0):
            N2 = O2 + lenON*np.array([np.cos(np.radians(t2)), np.sin(np.radians(t2))])
            dAN = np.linalg.norm(N2)
            if not (abs(lenCA-lenNC)+0.05 < dAN < lenCA+lenNC-0.05): continue
            a1 = (lenCA**2 - lenNC**2 + dAN**2)/(2*dAN)
            h2 = lenCA**2 - a1**2
            if h2 <= 0: continue
            hh = np.sqrt(h2); nrm = N2/dAN
            mid = a1*nrm; perp = np.array([-nrm[1], nrm[0]])
            for sgn in (1,-1):
                C2 = mid + sgn*hh*perp
                pts = [np.zeros(2), np.array([lenAB,0.0]), O2, N2, C2]
                angs=[]; ok=True
                for k in range(5):
                    p0, p1, p2 = pts[(k-1)%5], pts[k], pts[(k+1)%5]
                    v1, v2 = p0-p1, p2-p1
                    co = np.dot(v1,v2)/np.linalg.norm(v1)/np.linalg.norm(v2)
                    if abs(co)>1: ok=False; break
                    angs.append(np.degrees(np.arccos(co)))
                if not ok: continue
                cr=[]
                for k in range(5):
                    p0,p1,p2 = pts[k], pts[(k+1)%5], pts[(k+2)%5]
                    cr.append((p1[0]-p0[0])*(p2[1]-p1[1]) - (p1[1]-p0[1])*(p2[0]-p1[0]))
                if not (all(x>1e-9 for x in cr) or all(x<-1e-9 for x in cr)): continue
                score = -sum((angs[k]-targets[k])**2 for k in range(5))
                if best is None or score > best[0]:
                    best=(score, pts, angs, t1, t2)
    return best

tgt = [104.0, 104.0, 102.0, 105.0, 125.0]
best = build_ring(1.55, 1.44, 1.42, 1.28, 1.53, tgt)
print("pentagon score %.2f angles %s" % (best[0], np.round(best[2],1)))
pts2d = best[1]

HBOND = {7:0, 8:1, 9:2, 10:3, 11:3, 12:4, 13:4, 14:5, 15:6, 16:6}

def build_mol(els, coords):
    rw = Chem.RWMol()
    for e in els: rw.AddAtom(Chem.Atom(e))
    bl = [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5),(0,17),(17,18),(18,19),(19,1),(17,20)]
    for j,i in HBOND.items(): bl.append((i,j))
    for b in bl:
        rw.AddBond(int(b[0]), int(b[1]), Chem.BondType.SINGLE)
    m = rw.GetMol()
    Chem.SanitizeMol(m)
    m.GetAtomWithIdx(17).SetNoImplicit(True)
    conf = Chem.Conformer(21)
    for i in range(21): conf.SetAtomPosition(i, [float(v) for v in coords[i]])
    m.AddConformer(conf)
    return m

def make_geom(face):
    w = face*n
    A3 = X[A]
    ring3 = [A3 + p[0]*u + p[1]*w for p in pts2d]
    coords = np.zeros((21,3)); els=[None]*21
    for i,(el,src) in enumerate(work):
        els[i]=el; coords[i]=X[src]
    for i,e in zip([17,18,19,20], ["C","N","O","H"]): els[i]=e
    coords[17]=ring3[4]; coords[18]=ring3[3]; coords[19]=ring3[2]
    v1 = (ring3[0]-ring3[4]); v1/=np.linalg.norm(v1)
    v2 = (ring3[3]-ring3[4]); v2/=np.linalg.norm(v2)
    hd = -(v1+v2); hd/=np.linalg.norm(hd)
    coords[20] = ring3[4] + 1.09*hd
    return els, coords

def diag(els, c2, tag):
    P4 = np.array([c2[0], c2[1], c2[2], c2[5]])
    cc = P4.mean(axis=0)
    _,_,Vt = np.linalg.svd(P4-cc); nn = Vt[2]; nn/=np.linalg.norm(nn)
    if np.dot(c2[6]-cc, nn) < 0: nn = -nn
    sC = np.dot(c2[17]-cc, nn); sO = np.dot(c2[19]-cc, nn)
    print("%-14s d(1-2)=%.3f d(18-1)=%.3f d(20-2)=%.3f d(18-19)=%.3f d(19-20)=%.3f  sgn(C18)=%+.3f sgn(O20)=%+.3f"
          % (tag, np.linalg.norm(c2[0]-c2[1]), np.linalg.norm(c2[17]-c2[0]), np.linalg.norm(c2[19]-c2[1]),
             np.linalg.norm(c2[17]-c2[18]), np.linalg.norm(c2[18]-c2[19]), sC, sO))
    nonb = set()
    for i,j in [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(6,5),(0,17),(17,18),(18,19),(19,1),(17,20)]:
        nonb.add((min(i,j),max(i,j)))
    for j,i in HBOND.items(): nonb.add((min(i,j),max(i,j)))
    mn=99; pair=None
    for i in range(21):
        for j in range(i+1,21):
            if (i,j) in nonb: continue
            if els[i]!="H" and els[j]!="H": continue
            dd=np.linalg.norm(c2[i]-c2[j])
            if dd<mn: mn=dd; pair=(i+1,j+1)
    print("   min nonbonded H-contact %.3f between work atoms %s" % (mn, pair))
    return sC, sO

def write_xyz(path, els, coords, comment):
    with open(path,"w") as f:
        f.write("21\n%s\n"%comment)
        for i in range(21):
            f.write("%-2s %14.8f %14.8f %14.8f\n"%(els[i], coords[i,0], coords[i,1], coords[i,2]))

frag = [17,18,19,20]
def place(c2, dTarget1, dTarget2):
    def score(v):
        rot = v[:3]; tr = v[3:]
        th = np.linalg.norm(rot)
        if th < 1e-12: R = np.eye(3)
        else:
            k = rot/th; K = np.array([[0,-k[2],k[1]],[k[2],0,-k[0]],[-k[1],k[0],0]])
            R = np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K
        cen = c2[frag].mean(axis=0)
        Q = (R@(c2[frag]-cen).T).T + cen + tr
        return (np.linalg.norm(Q[0]-c2[0])-dTarget1)**2 + (np.linalg.norm(Q[2]-c2[1])-dTarget2)**2
    opt = minimize(score, np.zeros(6), method="Nelder-Mead",
                   options={"xatol":1e-9,"fatol":1e-14,"maxiter":40000,"maxfev":40000})
    rot = opt.x[:3]; tr = opt.x[3:]
    th = np.linalg.norm(rot)
    k = rot/th; K = np.array([[0,-k[2],k[1]],[k[2],0,-k[0]],[-k[1],k[0],0]])
    R = np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K
    cen = c2[frag].mean(axis=0)
    Q = (R@(c2[frag]-cen).T).T + cen + tr
    out = c2.copy(); out[frag] = Q
    return out, opt.fun

for face,name in [(+1,"exo"),(-1,"endo")]:
    els, coords = make_geom(face)
    m = build_mol(els, coords)
    ff = AllChem.MMFFGetMoleculeForceField(m, AllChem.MMFFGetMoleculeProperties(m))
    ff.Minimize(maxIts=50000)
    c2 = np.array(m.GetConformer().GetPositions())
    print("\n=== %s ==="%name)
    diag(els, c2, name+" product")
    write_xyz(os.path.join(OUT,"P_%s_start.xyz"%name), els, c2, "HL1 P_%s product start (MMFF)"%name)
    c3, res = place(c2, 2.25, 2.05)
    dab = np.linalg.norm(c3[0]-c3[1]); uu=(c3[1]-c3[0])/dab; sh=(dab-1.43)/2.0
    c3[0] = c3[0] + sh*uu; c3[1] = c3[1] - sh*uu
    diag(els, c3, name+" TSguess")
    write_xyz(os.path.join(OUT,"TSg_%s.xyz"%name), els, c3, "HL1 TS guess %s"%name)
    c4 = c3.copy(); c4[frag] = c3[frag] + 0.85*face*n
    diag(els, c4, name+" RCguess")
    write_xyz(os.path.join(OUT,"RCg_%s.xyz"%name), els, c4, "HL1 RC guess %s"%name)

tbl=[]
for i,(el,src) in enumerate(work): tbl.append([i+1, el, "norbornene atom %d"%(src+1)])
for i,e in zip([17,18,19,20],["C","N","O","H"]): tbl.append([i+1,e,"dipole"])
print("\nWORK ATOM TABLE (1-based):")
for t in tbl: print("  %2d %s  %s"%tuple(t))
print("map: work1=map4, work2=map5, work3=map6, work4=map7, work5=map8, work6=map9, work7=map10, work18=map1(Cdip), work19=map2(N), work20=map3(O)")
json.dump({"table":tbl,"map":{"1":4,"2":5,"3":6,"4":7,"5":8,"6":9,"7":10,"18":1,"19":2,"20":3}},
          open(os.path.join(OUT,"atom_table.json"),"w"), indent=1)
