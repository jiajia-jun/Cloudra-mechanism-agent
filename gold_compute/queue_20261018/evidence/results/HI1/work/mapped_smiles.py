import sys, numpy as np
from rdkit import Chem
from rdkit.Chem import rdDetermineBonds
sys.path.insert(0,'gold_compute/queue_20261018/results/HI1/work')
from geomlib import load_xyz, clean_xyz

# reactant: xyz order -> map numbers (heavy 1..14 = xyz order, migrating H (xyz 25) -> 15)
MAPS=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,None,None,None,None,None,None,None,None,None,None,15,None,None,None,None,None,None,None,None]
for tag,p in [('erythro','gold_compute/queue_20261018/results/HI1/geoms/HI1_erythro_R_min.xyz'),
              ('threo','gold_compute/queue_20261018/results/HI1/geoms/HI1_threo_R_min.xyz')]:
    at=load_xyz(p)
    m=Chem.MolFromXYZBlock(clean_xyz(at)); rdDetermineBonds.DetermineBonds(m,charge=0)
    Chem.AssignStereochemistryFrom3D(m,confId=0)
    for i,a in enumerate(m.GetAtoms()):
        if MAPS[i]: a.SetAtomMapNum(MAPS[i])
    smi=Chem.MolToSmiles(m)
    print(tag,'reactant mapped SMILES:'); print('   ',smi)
    # sanity: strip maps -> CIP
    m2=Chem.MolFromSmiles(smi)
    for a in m2.GetAtoms(): a.SetAtomMapNum(0)
    Chem.AssignStereochemistry(m2, cleanIt=True, force=True)
    print('    CIP:',[(a.GetIdx(),a.GetProp('_CIPCode')) for a in m2.GetAtoms() if a.HasProp('_CIPCode')], Chem.MolToSmiles(m2))
