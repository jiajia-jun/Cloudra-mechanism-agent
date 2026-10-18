
import glob, os
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
D="/home/ly/Cloudra-mechanism-agent/ts/ts_0037/structures"
for f in sorted(glob.glob(D+"/*.mol")):
    m=Chem.MolFromMolFile(f, sanitize=True, removeHs=False)
    if m is None:
        print(os.path.basename(f), "-> unparsable"); continue
    mh=Chem.RemoveHs(m)
    print(os.path.basename(f), "->", Chem.MolToSmiles(mh, isomericSmiles=True), rdMolDescriptors.CalcMolFormula(mh))
print()
decl_r="[CH:1]#[N+:2][O-:3].[CH:4]1=[CH:5][C@@H:6]2[CH2:7][CH2:8][C@H:9]1[CH2:10]2"
decl_p="[CH:1]1=[N:2][O:3][C@H:5]2[C@@H:4]1[C@H:9]1[CH2:8][CH2:7][C@@H:6]2[CH2:10]1"
for tag,s in [("declared reactant",decl_r),("declared product",decl_p)]:
    m=Chem.MolFromSmiles(s)
    mm=Chem.MolFromSmiles(Chem.MolToSmiles(m))
    print(tag,"stripped canonical:", Chem.MolToSmiles(mm, isomericSmiles=True))
