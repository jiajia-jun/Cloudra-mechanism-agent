from rdkit import Chem
for s in ["C=C[C@H](C)c1ccccc1.CN(C)O","C=C[C@@H](C)c1ccccc1.CN(C)O"]:
    m=Chem.MolFromSmiles(s)
    Chem.AssignStereochemistry(m, cleanIt=True, force=True)
    print(s,'->',[(a.GetIdx(),a.GetProp('_CIPCode')) for a in m.GetAtoms() if a.HasProp('_CIPCode')], Chem.MolToSmiles(m))
