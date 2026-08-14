import os
from typing import Any, Literal, Optional
from urllib.parse import quote

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.fs_utils import atomic_write_text

try:
    import httpx
    _HTTPX_AVAILABLE = True
except Exception:
    httpx = None
    _HTTPX_AVAILABLE = False

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    AllChem = None
    _RDKIT_AVAILABLE = False

_TIMEOUT = 15.0

description = (
    "Resolve a chemical name (common name / trade name / CAS / IUPAC) to a structure: try PubChem, NCI/CADD CIR, then OPSIN, "
    "and return SMILES, IUPAC name, formula, and InChIKey; optionally generate 3D coordinates into an xyz file for "
    "conformer_search / ts_guess / electronic_analysis. "
    "Use for: the user only gave a compound name (e.g. 'aspirin', 'Diels-Alder product', '50-78-2'). "
    "Do not use for: existing SMILES or structure files (use smiles_to_mol / format_converter). "
    "Note: Chinese common names hit poorly — retry with an English name, IUPAC name, or CAS; verify isomers by hand."
)


class NameToStructure_input_schema(input_schema):
    name: str = Field(description="Compound name. English common name, IUPAC name, CAS number, or trade name.")
    resolver: Literal["auto", "pubchem", "cir", "opsin"] = Field(
        default="auto",
        description="Resolver. auto falls back pubchem → cir → opsin; opsin specializes in systematic IUPAC names."
    )
    generate_3d: bool = Field(
        default=False,
        description="Whether to generate 3D coordinates from the resolved SMILES (RDKit ETKDG + MMFF)."
    )
    output_path: Optional[str] = Field(
        default=None,
        description="3D coordinate output path (.xyz). Default ./<name>.xyz when generate_3d=True."
    )


class NameToStructure_output_schema(output_schema):
    is_success: bool = Field(description="Whether resolution succeeded")
    smiles: str = Field(default="", description="Resolved SMILES (prefer isomeric SMILES with full stereochemistry)")
    iupac_name: str = Field(default="", description="IUPAC name (when the service returns it)")
    molecular_formula: str = Field(default="", description="Molecular formula (when PubChem returns it)")
    inchikey: str = Field(default="", description="InChIKey (when PubChem returns it)")
    cid: str = Field(default="", description="PubChem CID (when resolved via PubChem)")
    resolver_used: str = Field(default="", description="Resolver that succeeded (pubchem/cir/opsin)")
    xyz_path: str = Field(default="", description="3D coordinate file path (when generate_3d=True and successful)")
    message: str = Field(default="", description="Status or error message")


async def _resolve_pubchem(name: str) -> Optional[dict]:
    """PubChem PUG-REST：名称 → 属性 JSON。命中同义词库（通用名/商品名/CAS）。"""
    url = (f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(name, safe='')}"
           "/property/IsomericSMILES,CanonicalSMILES,IUPACName,MolecularFormula,InChIKey/JSON")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        return None
    props = resp.json().get("PropertyTable", {}).get("Properties", [])
    if not props:
        return None
    p = props[0]
    smiles = p.get("IsomericSMILES") or p.get("CanonicalSMILES") or p.get("ConnectivitySMILES", "")
    if not smiles:
        return None
    return {
        "smiles": smiles,
        "iupac_name": p.get("IUPACName", ""),
        "molecular_formula": p.get("MolecularFormula", ""),
        "inchikey": p.get("InChIKey", ""),
        "cid": str(p.get("CID", "")),
    }


async def _resolve_cir(name: str) -> Optional[dict]:
    """NCI/CADD Chemical Identifier Resolver：覆盖广（IUPAC/俗名/CAS/SMILES 皆可作输入）。"""
    base = f"https://cactus.nci.nlm.nih.gov/chemical/structure/{quote(name, safe='')}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{base}/smiles")
        if resp.status_code != 200 or not resp.text.strip():
            return None
        smiles = resp.text.strip().splitlines()[0].split()[0]
        iupac = ""
        try:
            r2 = await client.get(f"{base}/iupac_name")
            if r2.status_code == 200:
                iupac = r2.text.strip()
        except Exception:
            pass
    return {"smiles": smiles, "iupac_name": iupac}


async def _resolve_opsin(name: str) -> Optional[dict]:
    """OPSIN：IUPAC 系统命名专用解析器。"""
    url = f"https://opsin.ch.cam.ac.uk/opsin/{quote(name, safe='')}.json"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    smiles = data.get("smiles", "")
    if not smiles:
        return None
    return {"smiles": smiles, "inchikey": data.get("inchikey", "")}


class NameToStructure(Tool):
    tool_id: str = 't-46'
    tool_name: str = 'name_to_structure'
    tool_description: str = description
    input_schema: Any = NameToStructure_input_schema
    output_schema: Any = NameToStructure_output_schema

    def is_write(self) -> bool:
        return True

    @staticmethod
    def _smiles_to_xyz_file(smiles: str, output_path: str) -> None:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"RDKit could not parse SMILES: {smiles}")
        mol = Chem.AddHs(mol)
        if AllChem.EmbedMolecule(mol, AllChem.ETKDGv3()) != 0:
            raise ValueError("3D conformer embedding failed")
        try:
            AllChem.MMFFOptimizeMolecule(mol)
        except Exception:
            pass  # 个别元素无 MMFF 参数时保留未优化几何
        conf = mol.GetConformer()
        lines = [str(mol.GetNumAtoms()), f"Generated from SMILES: {smiles}"]
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            lines.append(f"{atom.GetSymbol():<4} {pos.x:>14.8f} {pos.y:>14.8f} {pos.z:>14.8f}")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        atomic_write_text(output_path, "\n".join(lines) + "\n")

    async def _resolve(self, name: str, resolver: str) -> tuple[Optional[dict], str, list[str]]:
        """按 resolver 策略解析，返回 (结果, 使用的服务, 失败记录)。"""
        attempts = {
            "pubchem": _resolve_pubchem,
            "cir": _resolve_cir,
            "opsin": _resolve_opsin,
        }
        order = list(attempts) if resolver == "auto" else [resolver]
        errors = []
        for svc in order:
            try:
                result = await attempts[svc](name)
            except Exception as e:
                errors.append(f"{svc}: {type(e).__name__} {e}")
                continue
            if result:
                return result, svc, errors
            errors.append(f"{svc}: no hit")
        return None, "", errors

    async def tool_call(self, user_input: NameToStructure_input_schema, session: Session) -> NameToStructure_output_schema:
        if not _HTTPX_AVAILABLE:
            return NameToStructure_output_schema(is_success=False, message="httpx is not installed.")

        name = user_input.name.strip()
        if not name:
            return NameToStructure_output_schema(is_success=False, message="name must not be empty")

        result, svc, errors = await self._resolve(name, user_input.resolver)
        if not result:
            hint = ("No resolver returned a hit. Suggestions: 1) use an English common name or IUPAC name "
                    "(Chinese trivial names rarely hit); 2) use a CAS number; 3) if the name describes a reaction "
                    "product (e.g. 'Diels-Alder product'), build it yourself with an RDKit reaction template.")
            return NameToStructure_output_schema(
                is_success=False,
                message=f"Name resolution failed: {name}\nAttempts: {'; '.join(errors)}\n{hint}",
            )

        smiles = result["smiles"]
        xyz_path = ""
        if user_input.generate_3d:
            if not _RDKIT_AVAILABLE:
                return NameToStructure_output_schema(
                    is_success=False, smiles=smiles, resolver_used=svc,
                    message="SMILES resolved, but 3D generation requires RDKit. Install it with: pip install 'cloudra[chem]'",
                )
            out = user_input.output_path or f"./{name.replace(' ', '_')}.xyz"
            try:
                self._smiles_to_xyz_file(smiles, out)
                xyz_path = out
            except Exception as e:
                return NameToStructure_output_schema(
                    is_success=False, smiles=smiles, resolver_used=svc,
                    iupac_name=result.get("iupac_name", ""),
                    message=f"SMILES resolved but 3D generation failed: {e}",
                )

        msg = f"Resolved ({svc}): {name} -> {smiles}"
        if svc == "cir":
            msg += " (CIR is a generic resolver; verify isomers/stereochemistry)"
        return NameToStructure_output_schema(
            is_success=True,
            smiles=smiles,
            iupac_name=result.get("iupac_name", ""),
            molecular_formula=result.get("molecular_formula", ""),
            inchikey=result.get("inchikey", ""),
            cid=result.get("cid", ""),
            resolver_used=svc,
            xyz_path=xyz_path,
            message=msg + ". Verify the structure matches expectations (isomers, stereochemistry, protonation state).",
        )


def get_class():
    return NameToStructure
