
import numpy as np, json
from rdkit import Chem
from rdkit.Chem import AllChem

SM = 'C1=CC2CCC1C2'
mol = Chem.AddHs(Chem.MolFromSmiles(SM))
ps = AllChem.ETKDGv3(); ps.randomSeed = 20261018
cid = AllChem.EmbedMolecule(mol, ps)
AllChem.MMFFOptimizeMolecule(mol, maxIters=5000)
conf = mol.GetConformer()
X = np.array(conf.GetPositions())
syms = [a.GetSymbol() for a in mol.GetAtoms()]
print('norbornene heavy idx -> element')
for i,(s) in enumerate(syms):
    if s!='H': print(i, s, np.round(X[i],4))

C4,C5,C6,C7,C8,C9,C10 = 0,1,2,3,4,5,6
alk_mid = 0.5*(X[C4]+X[C5])
u = X[C5]-X[C4]; u/=np.linalg.norm(u)
nrm = np.cross(X[C5]-X[C4], X[C6]-X[C4]); nrm/=np.linalg.norm(nrm)
if np.dot(nrm, X[C10]-alk_mid) < 0: nrm = -nrm
print('endo-face normal dot C10=', round(float(np.dot(nrm, X[C10]-alk_mid)),4))
print('|C4-C5| =', round(float(np.linalg.norm(X[C5]-X[C4])),4))

d_CN, d_NO, d_CH = 1.161, 1.207, 1.061
loc = {'C':np.array([0.,0.,0.]), 'N':np.array([d_CN,0.,0.]), 'O':np.array([d_CN+d_NO,0.,0.]), 'H':np.array([-d_CH,0.,0.])}

def build(face, dform=2.95):
    nf = nrm*face
    R = np.column_stack([u, nf, np.cross(u,nf)])
    Cpos = X[C4] + dform*nf
    frag = {k: Cpos + R@v for k,v in loc.items()}
    atoms = [(syms[i], X[i]) for i in range(len(syms))]
    atoms += [('C',frag['C']),('N',frag['N']),('O',frag['O']),('H',frag['H'])]
    return atoms, frag

for tag, face in (('exo',-1.0),('endo',+1.0)):
    atoms, frag = build(face)
    S=[a[0] for a in atoms]; P=np.array([a[1] for a in atoms])
    n1 = len(S)-4
    d_CC = np.linalg.norm(frag['C']-X[C4]); d_OC = np.linalg.norm(frag['O']-X[C5])
    argmin = min(((float(np.linalg.norm(frag[k]-X[i])), k, S[i]+str(i+1)) for k in frag for i in range(n1)))
    close = sorted([(round(float(np.linalg.norm(frag[k]-X[i])),3),k,S[i]+str(i+1)) for k in frag for i in range(n1) if np.linalg.norm(frag[k]-X[i])<2.4])
    print(tag,'d(C4..Cdip)=',round(float(d_CC),3),'d(C5..Odip)=',round(float(d_OC),3),'min inter-frag=',round(argmin[0],3),argmin[1:],'pairs<2.4A:',close[:8])
    out='gold_compute/queue_20261018/results/HL1/geoms/RC_%s.xyz'%tag
    with open(out,'w') as f:
        f.write('%d\nHL1 pre-reaction complex %s face | HCNO over C4=C5; atoms 1-17 norbornene, 18=C(dip) 19=N 20=O 21=H; SMILES: C#[N+][O-].C1=CC2CCC1C2\n'%(len(S),tag))
        for s,p in zip(S,P): f.write('%-3s %14.8f %14.8f %14.8f\n'%(s,p[0],p[1],p[2]))
    print(' wrote',out)
with open('gold_compute/queue_20261018/results/HL1/geoms/norbornene_mmff.xyz','w') as f:
    f.write('%d\nnorbornene MMFF seed | SMILES: C1=CC2CCC1C2\n'%len(syms))
    for i in range(len(syms)): f.write('%-3s %14.8f %14.8f %14.8f\n'%(syms[i],X[i][0],X[i][1],X[i][2]))
