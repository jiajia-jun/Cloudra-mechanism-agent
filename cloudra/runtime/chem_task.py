"""Typed internal chemistry tasks executed by the existing compute guard.

No arbitrary command, environment or executable is accepted. Engine termination
is recorded separately from usable geometry and scientific validation.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest
from cloudra.tools.core.conformer_selection import SamplingRequest
from cloudra.tools.core.ts_inputs import ScanGuess


class Solvation(CatalogModel):
    model: Literal['alpb','gbsa']
    solvent: str = Field(min_length=1)

    @model_validator(mode='after')
    def solvent_token(self):
        if not self.solvent[0].isalnum() or any(not (c.isascii() and (c.isalnum() or c in '._-')) for c in self.solvent):
            raise ValueError('solvent must be a native solvent name token')
        return self


class ChemTask(CatalogModel):
    task: Literal['xtb_path','xtb_opt','xtb_gradient','xtb_hessian','xtb_scan','rdkit_sampling']
    reactant_xyz: str
    product_xyz: str | None = None
    cpus: int = Field(ge=1)
    charge: int = 0
    multiplicity: int = Field(default=1,ge=1)
    solvation: Solvation | None = None
    mol_block: str | None = None
    sampling: SamplingRequest | None = None
    refinement_runs: int | None = Field(default=None,ge=1)
    scan: ScanGuess | None = None

    @model_validator(mode='after')
    def task_endpoints(self):
        if self.task == 'xtb_scan':
            if self.scan is None or self.scan.calculation.engine != 'xtb' or self.product_xyz is not None or self.refinement_runs is not None or self.solvation is not None or self.mol_block is not None or self.sampling is not None:
                raise ValueError('native scan requires its own typed declaration and one input XYZ')
        elif self.scan is not None:
            raise ValueError('scan declaration belongs only to xtb_scan')
        if self.task=='rdkit_sampling':
            if not self.mol_block or self.sampling is None or self.product_xyz is not None or self.refinement_runs is not None or self.solvation is not None:
                raise ValueError('sampling requires graph and typed sampling request only')
        elif self.mol_block is not None or self.sampling is not None:
            raise ValueError('native task rejects sampling parameters')
        if self.task=='xtb_path' and not self.product_xyz:
            raise ValueError('path task requires both endpoints')
        if self.task in ('xtb_opt', 'xtb_gradient', 'xtb_hessian') and (self.product_xyz is not None or self.refinement_runs is not None):
            raise ValueError('optimization task rejects path parameters')
        return self


def result_path(manifest_path: str) -> str:
    return str(Path(manifest_path).with_suffix('.chem-result.json'))


def run_task(manifest_path: str) -> int:
    from cloudra.tools.core.xtb_path_runner import XtbPathRequest, run_xtb_path
    path=Path(manifest_path).resolve()
    task=ChemTask.model_validate_json(path.read_text())
    if Path(result_path(str(path))).exists():
        data,_=read_task_result(str(path))
        return data['process_exit_code']
    os.environ['OMP_NUM_THREADS']=str(task.cpus)
    if task.task=='rdkit_sampling':
        result_data=_run_sampling(task)
        code=result_data['returncode']
    elif task.task=='xtb_path':
        result=run_xtb_path(XtbPathRequest(reactant_xyz=task.reactant_xyz,product_xyz=task.product_xyz,
            charge=task.charge,multiplicity=task.multiplicity,timeout=None,
            **({'refinement_runs': task.refinement_runs} if task.refinement_runs is not None else {}),
            output_dir=str(path.parent),run_label='queued_path',extra_args=['--gfn','2','--parallel',str(task.cpus),
            *([f'--{task.solvation.model}',task.solvation.solvent] if task.solvation else [])]))
        result_data=result.model_dump(mode='json')
        code=result.returncode if result.returncode is not None else 1
        result_data['returncode']=code
    elif task.task in ('xtb_gradient', 'xtb_hessian'):
        result_data=_run_native_evaluation(task,path)
        code=result_data['returncode']
    elif task.task == 'xtb_scan':
        from cloudra.tools.core.xtb_scan_runner import run_xtb_scan
        result_data=run_xtb_scan(task,path)
        code=result_data['returncode']
    else:
        result_data=_run_native_optimization(task,path)
        code=result_data['returncode']
    atomic_write_text(result_path(str(path)),json.dumps(dict(manifest_digest=content_digest(task.model_dump()),
        process_exit_code=code,artifact_root=str(path.parent),result=result_data),allow_nan=False))
    return code


def _run_sampling(task: ChemTask) -> dict:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.MolFromMolBlock(task.mol_block, removeHs=False)
    if mol is None:
        raise ValueError('sampling graph unreadable')
    request = task.sampling
    frames = []
    if request.method == 'ETKDGv3':
        parameters = AllChem.ETKDGv3()
        parameters.randomSeed = request.seed
        parameters.pruneRmsThresh = -1
        parameters.numThreads = task.cpus
        for cid in AllChem.EmbedMultipleConfs(mol, numConfs=request.count, params=parameters):
            frames.append(dict(positions=mol.GetConformer(cid).GetPositions().tolist(), transforms=None))
    else:
        from cloudra.tools.core.complex_assembly import AssemblyParameters, sample_independent_placements
        if mol.GetNumConformers() != 1:
            raise ValueError('rigid sampling requires one existing seed')
        groups = [list(group) for group in Chem.GetMolFrags(mol)]
        if len(groups) < 2:
            raise ValueError('rigid sampling requires multiple fragments')
        for placement in sample_independent_placements(mol, groups, seed=request.seed,
                count=request.count, parameters=AssemblyParameters()):
            frames.append(dict(positions=placement.positions, transforms=placement.fragment_transforms))
    return dict(returncode=0 if frames else 1, frames=frames,
                symbols=[a.GetSymbol() for a in mol.GetAtoms()], method=request.method,
                seed=request.seed, requested_count=request.count, optimization_attempted=False)


def _run_native_optimization(task: ChemTask, manifest: Path) -> dict:
    import subprocess

    from cloudra.tools.core import xtb_frames
    from cloudra.tools.core.run_dirs import next_run_dir
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    directory=Path(next_run_dir(str(manifest.parent),'native_optimization_runs','native_opt'))
    source=directory/'input.xyz'
    atomic_write_text(str(source),task.reactant_xyz)
    log=directory/'engine.out'
    argv=['xtb',str(source),'--gfn','2','--opt','--chrg',str(task.charge),
          '--uhf',str(task.multiplicity-1),'--parallel',str(task.cpus)]
    if task.solvation:
        argv.extend([f'--{task.solvation.model}',task.solvation.solvent])
    with log.open('w') as stream:
        process=subprocess.run(argv,cwd=str(directory),stdout=stream,stderr=subprocess.STDOUT,check=False)
    text=log.read_text(errors='replace')
    optimized=directory/'xtbopt.xyz'
    atoms=read_xyz_atoms(str(optimized)) if optimized.is_file() else None
    return dict(returncode=process.returncode,optimization_converged=xtb_frames.opt_converged(text),
        normal_termination=xtb_frames.normal_termination(text),energy_hartree=xtb_frames.final_energy_hartree(text),
        symbols=[s for s,_ in atoms] if atoms else [],positions=[p for _,p in atoms] if atoms else [],
        optimized_xyz=str(optimized) if atoms else None,log_file=str(log),command=argv)


def _run_native_evaluation(task: ChemTask, manifest: Path) -> dict:
    import subprocess

    from cloudra.tools.core import xtb_frames
    from cloudra.tools.core.run_dirs import next_run_dir
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.xtb_evaluation import read_gradient, read_hessian
    directory = Path(next_run_dir(str(manifest.parent), 'evaluation_runs', task.task))
    source = directory / 'input.xyz'
    atomic_write_text(str(source), task.reactant_xyz)
    atoms = read_xyz_atoms(str(source))
    symbols = [symbol for symbol, _ in atoms]
    positions = [point for _, point in atoms]
    log = directory / 'engine.out'
    argv = ['xtb', str(source), '--gfn', '2',
        '--grad' if task.task == 'xtb_gradient' else '--hess',
        '--chrg', str(task.charge), '--uhf', str(task.multiplicity - 1), '--parallel', str(task.cpus)]
    if task.solvation:
        argv.extend([f'--{task.solvation.model}', task.solvation.solvent])
    with log.open('w') as stream:
        process = subprocess.run(argv, cwd=str(directory), stdout=stream, stderr=subprocess.STDOUT, check=False)
    text = log.read_text(errors='replace')
    result = dict(returncode=process.returncode, normal_termination=xtb_frames.normal_termination(text),
        energy_hartree=xtb_frames.final_energy_hartree(text), method_fingerprint='GFN2-xTB',
        symbols=symbols, positions=positions, input_hash=content_digest(positions),
        command=argv, log_file=str(log), evaluation_valid=False, evaluation_error='')
    if process.returncode != 0 or not result['normal_termination'] or '#ERROR!' in text:
        result['evaluation_error'] = 'native evaluation did not terminate successfully'
        return result
    try:
        if task.task == 'xtb_gradient':
            if result['energy_hartree'] is None:
                raise ValueError('same-point energy is missing')
            result['gradient_file'] = str(directory / 'gradient')
            result.update(read_gradient(result['gradient_file'], symbols, positions))
        else:
            result['hessian_file'] = str(directory / 'hessian')
            result.update(read_hessian(result['hessian_file'], len(symbols)))
        result['evaluation_valid'] = True
    except (OSError, ValueError) as exc:
        result['evaluation_error'] = str(exc)
    return result


def read_task_result(manifest_path: str) -> tuple[dict,bool]:
    task=ChemTask.model_validate_json(Path(manifest_path).read_text())
    data=json.loads(Path(result_path(manifest_path)).read_text())
    if data.get('manifest_digest') != content_digest(task.model_dump()):
        raise ValueError('chemistry task result manifest digest mismatch')
    code=data.get('process_exit_code')
    if not isinstance(code,int) or isinstance(code,bool) or data.get('result',{}).get('returncode') != code:
        raise ValueError('chemistry task result lacks actual engine return code')
    origin = data.get('artifact_root')
    if origin is not None:
        root = Path(manifest_path).resolve().parent
        source = Path(origin)
        if not source.is_absolute():
            raise ValueError('chemistry task artifact root must be absolute')
        def local_path(value):
            if not value:
                return value
            relative = Path(value).relative_to(source)
            resolved = (root / relative).resolve()
            resolved.relative_to(root)
            return str(resolved)
        result = data['result']
        keys = ('run_dir', 'reactant_path', 'product_path', 'command_path',
                'path_input_path', 'versions_path', 'stdout_path', 'stderr_path',
                'path_xyz_path', 'ts_xyz_path', 'optimized_xyz', 'log_file', 'gradient_file', 'hessian_file',
                'scan_xyz_path', 'scan_input_path', 'input_xyz_path', 'candidate_path')
        for key in keys:
            if key in result:
                result[key] = local_path(result[key])
        for artifact in result.get('artifacts', []):
            artifact['path'] = local_path(artifact['path'])
        if 'partial_frames' in result:
            result['partial_frames'] = [local_path(value) for value in result['partial_frames']]
        for point in result.get('points', []):
            if point.get('frame_path'):
                point['frame_path'] = local_path(point['frame_path'])
        for candidate in result.get('candidates', []):
            candidate['frame_path'] = local_path(candidate['frame_path'])
        for relative, expected_hash in result.get('artifact_hashes', {}).items():
            import hashlib
            artifact = (root / relative).resolve()
            artifact.relative_to(root)
            if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f'chemistry task artifact digest mismatch: {relative}')
    return data,code==0


if __name__=='__main__':
    sys.exit(run_task(sys.argv[1]))
