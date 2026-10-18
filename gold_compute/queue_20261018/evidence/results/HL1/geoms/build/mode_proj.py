
import numpy as np, re, sys
p=sys.argv[1]
L=open(p).read().splitlines()
# find imaginary frequency line
for i,l in enumerate(L):
    if 'Frequencies --' in l and '-' in l.split('--')[1]:
        fi=i; break
print("imag line", fi+1, L[fi])
freqs=[float(x) for x in L[fi].split('--')[1].split()]
neg=[j for j,f in enumerate(freqs) if f<0]
print("negative freqs on that line:", [(j,freqs[j]) for j in neg])
col=neg[0]
# read displacement block: find start after fi
j=fi
while 'Atom  AN' not in L[j]: j+=1
start=j+1
disp={}
for k in range(start, start+21):
    f=L[k].split()
    a=int(f[0]); an=int(f[1])
    xyz=[float(x) for x in f[2+3*col:5+3*col]]
    disp[a]=np.array(xyz)
# geometry: last standard orientation
idx=[i for i,l in enumerate(L) if 'Standard orientation' in l]
st=idx[-1]; j=st+5; co={}
while not L[j].strip().startswith('---'):
    f=L[j].split(); co[int(f[0])]=np.array([float(f[3]),float(f[4]),float(f[5])]); j+=1
tot=sum(np.dot(disp[a],disp[a]) for a in disp)
print("sum |d|^2 = %.6f (normalisation)"%tot)
for a,b in [(18,1),(20,2),(1,2),(18,19),(19,20)]:
    u=co[b]-co[a]; r=np.linalg.norm(u); u/=r
    proj=np.dot(disp[a]-disp[b], u)
    print("pair (%2d,%2d) r=%.3f  bond-stretch projection = %+0.4f (mode-norm units)"%(a,b,r,proj))
fr=[(a,float(np.dot(disp[a],disp[a])/tot)) for a in disp]
fr.sort(key=lambda t:-t[1])
print("top atom fractions:", [(a,round(v,4)) for a,v in fr[:6]])
atoms=set([18,1,20,2,19])
print("reaction-centre atom fraction {1,2,18,19,20}:", round(sum(v for a,v in fr if a in atoms),4))
