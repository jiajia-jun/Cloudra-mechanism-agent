"""Parse Gaussian frequency log normal modes and compute signed bond projections
for the imaginary mode (D1 (a) direction check) + composition fractions (D1 (b))."""
import sys, re, numpy as np

def parse_modes(path):
    lines=open(path, errors='ignore').read().splitlines()
    modes=[]; freqs=[]
    i=0
    while i < len(lines):
        L=lines[i]
        if 'Frequencies --' in L:
            f=[float(x) for x in L.split('--')[1].split()]
            freqs.extend(f)
            j=i+5   # first atom row
            disp={}
            while j < len(lines) and not lines[j].strip().startswith('Frequencies --'):
                parts=lines[j].split()
                if len(parts)==11 and parts[0].isdigit():
                    a=int(parts[0])
                    v=[float(x) for x in parts[2:11]]
                    disp[a]=v
                j+=1
            modes.append(disp)
            i=j
        else:
            i+=1
    return freqs, modes

def analyze(log, natoms, pairs, label):
    freqs, modes = parse_modes(log)
    print('==',label,'nmodes',len(freqs),'first',freqs[0])
    # first block holds modes 1..3 ; imag mode = freqs[0]
    blk=modes[0]
    # also need coordinates: take the last "Standard orientation"/"Input orientation" block
    lines=open(log, errors='ignore').read().splitlines()
    coords=None
    for i,L in enumerate(lines):
        if 'Input orientation' in L or 'Standard orientation' in L:
            try:
                start=i+5; c={}
                for k in range(natoms):
                    p=lines[start+k].split()
                    c[int(p[0])]=np.array([float(p[3]),float(p[4]),float(p[5])])
                coords=c
            except Exception: pass
    # displacement vector of mode 1 from the first block columns 0..2
    d={a: np.array(blk[a][0:3]) for a in blk}
    tot=sum(float(np.dot(v,v)) for v in d.values())
    print('  sum d^2 = %.4f (before normalisation)'%tot)
    for (i,j) in pairs:
        u=coords[j]-coords[i]; u=u/np.linalg.norm(u)
        rel=d[j]-d[i]
        proj=float(np.dot(rel,u))
        print('  pair (%d,%d): d(coords)=%.3f A ; rel disp=%.4f ; signed proj on bond dir (i->j)=%+.4f'%(
            i,j,np.linalg.norm(coords[j]-coords[i]), np.linalg.norm(rel), proj))
    frac={a: float(np.dot(v,v))/tot for a,v in d.items()}
    top=sorted(frac.items(), key=lambda kv:-kv[1])[:5]
    print('  atom fractions:',[(a, round(f,4)) for a,f in top])
    heavy=[a for a in frac if a in (1,2,3,4,5,6,7,8,9,10,11,12,13,14)]
    print('  heavy-atom fraction sum = %.4f'%sum(frac[a] for a in heavy))
    return freqs

if __name__=='__main__':
    log=sys.argv[1]; natoms=int(sys.argv[2]); pairs=[tuple(int(x) for x in p.split(',')) for p in sys.argv[3].split(';')]
    analyze(log,natoms,pairs,sys.argv[4] if len(sys.argv)>4 else log)
