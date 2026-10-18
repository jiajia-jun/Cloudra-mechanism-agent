from rdkit import Chem
prod_Z="[CH3:1]/[CH:2]=[C:7](\\[c:9]1[cH:10][cH:11][cH:12][cH:13][cH:14]1)[CH3:8].[CH3:4][N:3]([CH3:5])[O:6][H:15]"
prod_E="[CH3:1]/[CH:2]=[C:7](/[c:9]1[cH:10][cH:11][cH:12][cH:13][cH:14]1)[CH3:8].[CH3:4][N:3]([CH3:5])[O:6][H:15]"
for nm,s in [('Z',prod_Z),('E',prod_E)]:
    m=Chem.MolFromSmiles(s)
    print(nm,'parsed',m is not None, m.GetNumAtoms())
    st=[str(b.GetStereo()) for b in m.GetBonds() if b.GetBondType()==Chem.BondType.DOUBLE]
    print('   stereo:',st)
    for a in m.GetAtoms(): a.SetAtomMapNum(0)
    print('   no-map:',Chem.MolToSmiles(m))
