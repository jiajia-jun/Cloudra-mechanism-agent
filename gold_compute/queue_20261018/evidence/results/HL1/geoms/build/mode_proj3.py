
import numpy as np, sys
p=sys.argv[1]
L=open(p).read().splitlines()
for i,l in enumerate(L):
    if 'Frequencies --' in l and '-' in l.split('--')[1]: fi=i; break
print("imag line L%d: %s"%(fi+1, L[fi].strip()))
j=fi
while 'Atom  AN' not in L[j]: j+=1
disp={}
for k in range(j+1, j+22):
    f=L[k].split(); disp[int(f[0])]=np.array([float(x) for x in f[2:5]])
idx=[i for i,l in enumerate(L) if 'Standard orientation' in l]
st=idx[-1]; j=st+5; co={}; el={}
Z={1:1.008,6:12.011,7:14.007,8:15.999}
while not L[j].strip().startswith('---'):
    f=L[j].split(); co[int(f[0])]=np.array([float(f[3]),float(f[4]),float(f[5])]); el[int(f[0])]=int(f[1]); j+=1
tot=sum(np.dot(disp[a],disp[a]) for a in disp)
fr=sorted([(a,float(np.dot(disp[a],disp[a])/tot)) for a in disp], key=lambda t:-t[1])
print("max single-atom share: atom %d (%s) = %.4f"%(fr[0][0], {1:'H',6:'C',7:'N',8:'O'}[el[fr[0][0]]], fr[0][1]))
print("top5:", [(a,round(v,4)) for a,v in fr[:5]])
print("reaction-centre {1,2,18,19,20}: %.4f"%sum(v for a,v in fr if a in (1,2,18,19,20)))
heavy=[a for a in co if el[a]!=1]
print("heavy-atom share: %.4f"%sum(dict(fr)[a] for a in heavy))
# sign: make the forming pairs positive
def proj(sgn,a,b):
    u=co[b]-co[a]; r=np.linalg.norm(u); u/=r
    d=(sgn*disp[a]/np.sqrt(Z[el[a]]) - sgn*disp[b]/np.sqrt(Z[el[b]]))
    return np.dot(d,u), r
s1,_=proj(1,18,1)
sgn = 1 if s1>0 else -1
print("sign chosen so that (18,1) shortens: sgn=%d"%sgn)
for a,b,lab in [(18,1,"C_HCNO...C4"),(20,2,"O...C5"),(1,2,"C4=C5"),(18,19,"C#N"),(19,20,"N-O")]:
    pv,rr=proj(sgn,a,b)
    print("   pair(%2d,%2d) %-12s r=%.3f  projection = %+0.4f A"%(a,b,lab,rr,pv))
