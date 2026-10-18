
import numpy as np, re, sys, itertools
def lastframe(p):
    L=open(p).read().splitlines()
    idx=[i for i,l in enumerate(L) if 'Standard orientation' in l] or [i for i,l in enumerate(L) if 'Input orientation' in l]
    st=idx[-1]; j=st+5; co=[]; els=[]
    Z={1:'H',6:'C',7:'N',8:'O'}
    while not L[j].strip().startswith('---'):
        f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); els.append(Z[int(f[1])]); j+=1
    return np.array(co), els, st+1
def kabsch_rmsd(A,B):
    Ac=A-A.mean(0); Bc=B-B.mean(0)
    U,S,Vt=np.linalg.svd(Ac.T@Bc)
    d=np.sign(np.linalg.det(U@Vt))
    D=np.diag([1,1,d])
    R=U@D@Vt
    Ar=Ac@R
    dev=np.linalg.norm(Ar-Bc,axis=1)
    return np.sqrt((dev**2).mean()), dev
refs={"P-endo(#1228)":"/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/jobs/HL1_P_exo_optfreq.log",
      "P-exo(#1229)":"/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1/jobs/HL1_P_endo_optfreq.log"}
R={}
for k,v in refs.items():
    co,els,l=lastframe(v); R[k]=(co,els,l)
for q in sys.argv[1:]:
    co,els,l=lastframe(q)
    print("### %s  (last frame block at L%d)"%(q.split('/')[-1], l-4))
    for k,(rco,rels,rl) in R.items():
        assert rels==els, (k, "element mismatch")
        rms,dev=kabsch_rmsd(co,rco)
        i=np.argmax(dev)
        print("   vs %-14s RMSD(all 21 atoms) = %.4f A ; max atom dev = %.4f A at atom %d (%s)"%(k,rms,dev[i],i+1,els[i]))
    P4=np.array([co[0],co[1],co[2],co[5]]); cc=P4.mean(0)
    _,_,Vt=np.linalg.svd(P4-cc); nn=Vt[2]; nn/=np.linalg.norm(nn)
    if np.dot(co[6]-cc,nn)<0: nn=-nn
    print("   sdist(18)=%+.4f  d(7,18)=%.4f  d(1,18)=%.4f  d(2,20)=%.4f  d(1,2)=%.4f"%(np.dot(co[17]-cc,nn),np.linalg.norm(co[6]-co[17]),np.linalg.norm(co[0]-co[17]),np.linalg.norm(co[1]-co[19]),np.linalg.norm(co[0]-co[1])))
