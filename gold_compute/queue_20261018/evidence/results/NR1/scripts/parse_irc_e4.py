import re, math, json, os
p="/home/ly/Cloudra-mechanism-agent/ts/ts_0042/jobs/declaration_0002/irc/irc.log"
L=open(p).read().split("\n")
scf=[(i+1,float(m.group(1))) for i,l in enumerate(L) for m in [re.search(r"SCF Done:\s+E\(RB3LYP\) =\s+(-?\d+\.\d+)",l)] if m]
blocks=[]
for i,l in enumerate(L):
    if "Input orientation:" in l:
        j=i+5; at=[]
        while j<len(L) and re.match(r"\s*-+\s*$",L[j])==None:
            q=L[j].split()
            if len(q)==6: at.append((int(q[0]),float(q[3]),float(q[4]),float(q[5])))
            j+=1
        blocks.append((i+1,at))
# direction markers: "Point Number N in FORWARD/REVERSE path direction"
marks=[]
for i,l in enumerate(L):
    m=re.search(r"Point Number\s+(\d+) in (FORWARD|REVERSE) path direction",l)
    if m: marks.append((i+1,int(m.group(1)),m.group(2)))
def dist(c,a,b): return math.dist(c[a],c[b])
def dih(p0,p1,p2,p3):
    b1=[p2[i]-p1[i] for i in range(3)]; b0=[p0[i]-p1[i] for i in range(3)]; b2=[p3[i]-p2[i] for i in range(3)]
    def cross(u,v): return [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    def dot(u,v): return sum(x*y for x,y in zip(u,v))
    def norm(u): return math.sqrt(dot(u,u))
    b1n=[x/norm(b1) for x in b1]
    v=[b0[i]-dot(b0,b1n)*b1n[i] for i in range(3)]
    w=[b2[i]-dot(b2,b1n)*b1n[i] for i in range(3)]
    return math.degrees(math.atan2(dot(cross(b1n,v),w),dot(v,w)))
ETS=-169.641371451
rows=[]
for (ln,pn,dirn) in marks:
    e=next((v for (l2,v) in scf if l2>ln),None)
    bl=next(((l2,at) for (l2,at) in blocks if l2>ln),None)
    c={a[0]:(a[1],a[2],a[3]) for a in bl[1]}
    rows.append(dict(dir=dirn,point=pn,line=bl[0],E=e,
      N1H4=dist(c,1,4),O3H4=dist(c,3,4),C2O3=dist(c,2,3),N1C2=dist(c,1,2),
      O3H6=dist(c,3,6),C2H5=dist(c,2,5),
      dih4=dih(c[4],c[1],c[2],c[3]),dih6=dih(c[6],c[3],c[2],c[1])))
print("dir p  line  E/Ha             dE_TS  N1-H4  O3-H4  C2-O3  N1-C2  O3-H6  C2-H5  dih4   dih6")
for r in rows:
    print("%s %2d %5d %.9f %+7.2f %6.3f %6.3f %6.3f %6.3f %6.3f %6.3f %7.1f %7.1f"%(r["dir"][:1],r["point"],r["line"],r["E"],(r["E"]-ETS)*627.5095,r["N1H4"],r["O3H4"],r["C2O3"],r["N1C2"],r["O3H6"],r["C2H5"],r["dih4"],r["dih6"]))
# RMSD vs seeds
def readxyz(fp):
    ls=open(fp).read().split("\n")
    n=int(ls[0]); out=[]
    for l in ls[2:2+n]:
        q=l.split(); out.append((q[0],float(q[1]),float(q[2]),float(q[3])))
    return out
def kabsch_rmsd(a,b):
    import numpy as np
    A=np.array([(p[1],p[2],p[3]) for p in a]); B=np.array([(p[1],p[2],p[3]) for p in b])
    assert [p[0] for p in a]==[p[0] for p in b]
    A=A-A.mean(0); B=B-B.mean(0)
    H=A.T@B; U,S,Vt=np.linalg.svd(H); d=np.sign(np.linalg.det(Vt.T@U.T))
    D=np.diag([1,1,d]); R=Vt.T@D@U.T
    Ar=(R@A.T).T
    heavy=[i for i,p in enumerate(a) if p[0]!="H"]
    return float(np.sqrt(((Ar-B)**2).sum(1).mean())), float(np.sqrt(((Ar[heavy]-B[heavy])**2).sum(1).mean()))
ROOT="/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/NR1/geoms/"
init=readxyz(ROOT+"opt/INT1c.xyz"); pc=readxyz(ROOT+"E4_P_complex.xyz")
last={}
for d in ("FORWARD","REVERSE"):
    bl=next(((l2,at) for (l2,at) in blocks if l2> [m[0] for m in marks if m[2]==d][-1]),None)
    last[d]=[(chr(0),)+tuple(x) for x in []]
    atoms=[(("N" if False else ""),)+ (a[1],a[2],a[3]) for a in bl[1]]
    sym=["N","C","O","H","H","H"]
    g=[(sym[i],bl[1][i][1],bl[1][i][2],bl[1][i][3]) for i in range(6)]
    for name,ref in (("INT1c",init),("P_complex",pc)):
        try:
            rms,rh=kabsch_rmsd(g,ref); print("last %s frame vs %s : RMSD_all=%.3f A  heavy=%.3f A"%(d,name,rms,rh))
        except Exception as ex: print("rmsd fail",ex)
    d4=dih((g[3][1],g[3][2],g[3][3]),(g[0][1],g[0][2],g[0][3]),(g[1][1],g[1][2],g[1][3]),(g[2][1],g[2][2],g[2][3]))
    d6=dih((g[5][1],g[5][2],g[5][3]),(g[2][1],g[2][2],g[2][3]),(g[1][1],g[1][2],g[1][3]),(g[0][1],g[0][2],g[0][3]))
    print("last %s frame dih(H4-N1-C2-O3)=%.1f  dih(H6-O3-C2-N1)=%.1f"%(d,d4,d6))
json.dump(rows,open("/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/NR1/scripts/irc_rows.json","w"),indent=1)
