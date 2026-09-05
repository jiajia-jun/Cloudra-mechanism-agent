from rdkit import Chem
from rdkit.Chem import AllChem
import numpy as np, os

os.chdir("/Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA2_aldol_20260905/campaign/xtb")

def embed(smi, n=20, seed=0x1234):
    m = Chem.AddHs(Chem.MolFromSmiles(smi))
    ps = AllChem.ETKDGv3(); ps.randomSeed = seed
    cids = AllChem.EmbedMultipleConfs(m, numConfs=n, params=ps)
    best, be = None, 1e9
    for cid in cids:
        try:
            mp = AllChem.MMFFGetMoleculeProperties(m)
            ff = AllChem.MMFFGetMoleculeForceField(m, mp, confId=cid)
            ff.Minimize(maxIts=1000)
            e = ff.CalcEnergy()
            if e < be: best, be = cid, e
        except Exception: pass
    return m, best

def xyz(m, cid, comment):
    conf = m.GetConformer(cid)
    lines = [f"{m.GetNumAtoms()}", comment]
    for at in m.GetAtoms():
        p = conf.GetAtomPosition(at.GetIdx())
        lines.append(f"{at.GetSymbol():2s} {p.x: .6f} {p.y: .6f} {p.z: .6f}")
    return "\n".join(lines) + "\n"

def save(m, cid, name, comment):
    open(name + ".xyz", "w").write(xyz(m, cid, comment))

# --- species as supramolecular clusters (same atom count C4H9O3- = 16 atoms)
# rc  : [OH-].CC=O.CC=O   (hydroxide + 2 acetaldehyde)
rc, rc_c = embed("[OH-].CC=O.CC=O")
save(rc, rc_c, "rc_raw", "smiles: [OH-].CC=O.CC=O  node=rc  charge=-1 mult=1")
# i1  : enolate A + water + aldehyde B  = [CH2-]C=O.O.CC=O
i1, i1_c = embed("[CH2-]C=O.O.CC=O")
save(i1, i1_c, "i1_raw", "smiles: [CH2-]C=O.O.CC=O  node=i1  charge=-1 mult=1")
# i2  : aldol alkoxide + water = CC([O-])CC=O.O
i2, i2_c = embed("CC([O-])CC=O.O")
save(i2, i2_c, "i2_raw", "smiles: CC([O-])CC=O.O  node=i2  charge=-1 mult=1")
# p   : [OH-].CC(O)CC=O
p, p_c = embed("[OH-].CC(O)CC=O")
save(p, p_c, "p_raw", "smiles: [OH-].CC(O)CC=O  node=p  charge=-1 mult=1")

print("saved rc_raw i1_raw i2_raw p_raw")
