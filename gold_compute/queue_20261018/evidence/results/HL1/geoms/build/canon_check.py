
from rdkit import Chem
def canon(s):
    m=Chem.MolFromSmiles(s)
    for a in m.GetAtoms(): a.SetAtomMapNum(0)
    return Chem.MolToSmiles(m, isomericSmiles=True)
decl_r="[CH:1]#[N+:2][O-:3].[CH:4]1=[CH:5][C@@H:6]2[CH2:7][CH2:8][C@H:9]1[CH2:10]2"
decl_p="[CH:1]1=[N:2][O:3][C@H:5]2[C@@H:4]1[C@H:9]1[CH2:8][CH2:7][C@@H:6]2[CH2:10]1"
per_r="C#[N+][O-].C1=C[C@H]2CC[C@@H]1C2"
per_p="C1=NO[C@@H]2[C@@H]3CC[C@@H](C3)[C@H]12"
print("reactant declared canon:", canon(decl_r))
print("reactant perceived canon:", canon(per_r))
print("MATCH reactant:", canon(decl_r)==canon(per_r))
print("product  declared canon:", canon(decl_p))
print("product  perceived canon:", canon(per_p))
print("MATCH product :", canon(decl_p)==canon(per_p))
# also ts_0036 exo product
decl_p36="[CH:1]1=[N:2][O:3][C@@H:5]2[C@H:4]1[C@H:9]1[CH2:8][CH2:7][C@@H:6]2[CH2:10]1"
per_p36="C1=NO[C@H]2[C@@H]3CC[C@@H](C3)[C@@H]12"
print("36 product declared:", canon(decl_p36)); print("36 product perceived:", canon(per_p36)); print("MATCH:", canon(decl_p36)==canon(per_p36))
