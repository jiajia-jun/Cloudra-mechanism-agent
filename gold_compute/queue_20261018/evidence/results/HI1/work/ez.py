from rdkit import Chem
for smi in ["C/C=C(\\C)c1ccccc1","C/C=C(/C)c1ccccc1","CC=C(C)c1ccccc1"]:
    m=Chem.MolFromSmiles(smi)
    print(smi,'->',Chem.MolToSmiles(m), [ (b.GetStereo()) for b in m.GetBonds() if b.GetBondType()==Chem.BondType.DOUBLE])
