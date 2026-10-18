
import numpy as np, sys
p="/home/ly/Cloudra-mechanism-agent/ts/ts_0036/jobs/declaration_0006/frequency/frequency.log"
L=open(p).read().splitlines()
for i,l in enumerate(L):
    if 'Frequencies --' in l and '-' in l.split('--')[1]: fi=i; break
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
for sgn,lab in [(+1,"sign A (as printed)"),(-1,"sign B (global flip)")]:
    print(lab)
    for a,b in [(18,1),(20,2),(1,2),(18,19),(19,20)]:
        u=co[b]-co[a]; r=np.linalg.norm(u); u/=r
        d=(sgn*disp[a]/np.sqrt(Z[el[a]]) - sgn*disp[b]/np.sqrt(Z[el[b]]))
        print("   pair(%2d,%2d) r=%.3f  projection = %+0.4f Angstrom (mass-weighted, sum m|dx|^2=1)"%(a,b,r,np.dot(d,u)))
