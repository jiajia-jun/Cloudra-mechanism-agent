
import sys,numpy as np
def lastframe(p):
    L=open(p).read().splitlines()
    idx=[i for i,l in enumerate(L) if 'Standard orientation' in l] or [i for i,l in enumerate(L) if 'Input orientation' in l]
    st=idx[-1]; j=st+5; co=[]
    while not L[j].strip().startswith('---'):
        f=L[j].split(); co.append([float(f[3]),float(f[4]),float(f[5])]); j+=1
    return np.array(co), st+1
a,la=lastframe(sys.argv[1]); b,lb=lastframe(sys.argv[2])
print("opt last frame block L%d ; freq frame block L%d"%(la,lb))
d=np.linalg.norm(a-b,axis=1)
print("max |diff| = %.4f A at atom %d ; rms = %.4f"%(d.max(), d.argmax()+1, np.sqrt((d**2).mean())))
print("opt  d(1,18)=%.3f d(2,20)=%.3f ; freq d(1,18)=%.3f d(2,20)=%.3f"%(np.linalg.norm(a[0]-a[17]),np.linalg.norm(a[1]-a[19]),np.linalg.norm(b[0]-b[17]),np.linalg.norm(b[1]-b[19])))
