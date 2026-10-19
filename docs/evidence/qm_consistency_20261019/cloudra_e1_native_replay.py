"""Read-only native E1 proof replay. No QM engine, model API, or tolerance edits."""
# ruff: noqa: E402 -- initialize isolated config before importing Cloudra.

# Audit bootstrap: locate the checkout and keep generated files/configuration in /tmp.
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.dont_write_bytecode = True
_AUDIT_CONTEXT = Path(tempfile.mkdtemp(prefix="cloudra-audit-context-", dir="/tmp"))
os.environ["CLOUDRA_CONFIG_FILE"] = str(_AUDIT_CONTEXT / "absent.yaml")
os.environ["CLOUDRA_DATA_DIR"] = str(_AUDIT_CONTEXT / "runtime")
os.environ["CLOUDRA_DAEMON_WATCHDOG"] = "off"
os.chdir(_AUDIT_CONTEXT)

import argparse
import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence_dir', type=Path, help='Absolute path to extracted E1 evidence, including SHA256SUMS')
args = parser.parse_args()
if not args.evidence_dir.is_absolute():
    parser.error('evidence_dir must be absolute because the probe isolates its working directory')
SOURCE = args.evidence_dir
ARTIFACT = _AUDIT_CONTEXT / 'e1_native_replay.json'
WORK = Path(tempfile.mkdtemp(prefix='cloudra-e1-native-replay-', dir='/tmp'))
WORKSPACE = WORK/'workspace'
os.environ['CLOUDRA_CONFIG_FILE'] = str(WORK/'missing-config.yaml')
os.environ['CLOUDRA_DATA_DIR'] = str(WORK/'runtime')
os.environ['CLOUDRA_DAEMON_WATCHDOG'] = 'off'
logging.disable(logging.CRITICAL)
from cloudra.dag.file_science import _geometry_species
from cloudra.tools.core.irc_evidence import (
    _optimization_geometries,
    _optimized_minima,
    irc_endpoint_geometries,
    irc_start_geometry,
    normal_log,
    verify_short_irc_direction,
)
from cloudra.tools.core.irc_path import same_geometry
from cloudra.tools.core.qm_log_facts import read_qm_log


def digest_tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}
original_hashes = digest_tree(SOURCE)
shutil.copytree(SOURCE, WORKSPACE)
manifest_ok = []
for line in (SOURCE/'SHA256SUMS').read_text().splitlines():
    if line.strip():
        digest, name = line.split(maxsplit=1)
        name = name.lstrip('*')
        manifest_ok.append(hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() == digest)
rows=json.loads((WORKSPACE/'tool_calls/seq_4761.json').read_text())
original_request=next(item for item in rows if item['phase']=='request')
original_result=json.loads(next(item['result'] for item in rows if item['phase']=='result'))
arguments=original_request['arguments']
delivered=json.loads((WORKSPACE/'mechanism_graph.json').read_text())
source_smiles=next(node['smiles'][0] for node in delivered['nodes'] if node['role']=='reactant')
target_smiles=next(node['smiles'][0] for node in delivered['nodes'] if node['role']=='product')
result={'source':str(SOURCE),'workspace':str(WORKSPACE),'manifest_entries_valid':all(manifest_ok),
        'original_request_seq':original_request['seq'],'original_result_seq':4761,
        'original_arguments':arguments,'original_scientific_checks':original_result['result']['scientific_checks'],
        'facts':{},'identities':{}}
paths={key:WORKSPACE/'calc'/name for key,name in {
    'ts':'ts1.log','irc':'irc3.log','source_opt_freq':'endpoint_rev5.log',
    'target_opt_freq':'endpoint_fwd5.log','delivered_source':'rc2.log'}.items()}
parsed={}
for key,path in paths.items():
    facts=read_qm_log(path)
    parsed[key]=facts
    result['facts'][key]={'path':str(path.relative_to(WORKSPACE)),
        'normal_termination':facts.normal_termination,'normal_log':normal_log(path),
        'opt_converged':facts.opt_converged,
        'frequencies_present':facts.frequencies_cm is not None,
        'n_imag':None if facts.frequencies_cm is None else sum(freq<0 for freq in facts.frequencies_cm),
        'imaginary_frequencies':None if facts.frequencies_cm is None else [freq for freq in facts.frequencies_cm if freq<0],
        'energy_hartree':facts.electronic_energy_hartree,
        'atom_count':None if facts.geometry is None else len(facts.geometry[0]),
        'job_types':sorted(facts.job_types)}
    print('FACT',key,json.dumps(result['facts'][key]),flush=True)
for key,smiles in [('source_opt_freq',source_smiles),('delivered_source',source_smiles),('target_opt_freq',target_smiles)]:
    result['identities'][key]={'smiles':smiles,'matches':_geometry_species(str(paths[key]),smiles)}
ends=irc_endpoint_geometries(paths['irc'])
source_opt=_optimization_geometries(paths['source_opt_freq'])
target_opt=_optimization_geometries(paths['target_opt_freq'])
source_details=[]
target_details=[]
source_minima=_optimized_minima([paths['source_opt_freq']],smiles=source_smiles,side='SOURCE',charge=-1,details=source_details)
target_minima=_optimized_minima([paths['target_opt_freq']],smiles=target_smiles,side='TARGET',charge=-1,details=target_details)
result['prerequisites']={
    'irc_two_sides_present':ends is not None,
    'irc_start_matches_ts':same_geometry(irc_start_geometry(paths['irc']),parsed['ts'].geometry),
    'source_qualified_opt_freq_count':len(source_minima),'target_qualified_opt_freq_count':len(target_minima),
    'source_qualified_details':source_details,'target_qualified_details':target_details,
    'source_opt_final_matches_own_freq_geometry':same_geometry(source_opt[1],parsed['source_opt_freq'].geometry),
    'target_opt_final_matches_own_freq_geometry':same_geometry(target_opt[1],parsed['target_opt_freq'].geometry),
    'source_rev5_final_matches_rc2_final':same_geometry(parsed['source_opt_freq'].geometry,parsed['delivered_source'].geometry),
    'source_opt_start_matches_irc_side_0':same_geometry(source_opt[0],ends[0]),
    'source_opt_start_matches_irc_side_1':same_geometry(source_opt[0],ends[1]),
    'target_opt_start_matches_irc_side_0':same_geometry(target_opt[0],ends[0]),
    'target_opt_start_matches_irc_side_1':same_geometry(target_opt[0],ends[1]),
}
passed,details=verify_short_irc_direction(paths['irc'],[paths['ts']],
    [paths['target_opt_freq']],[paths['source_opt_freq']],charge=-1,
    reactant_smiles=source_smiles,product_smiles=target_smiles)
result['direct_verifier']={'passed':passed,'details':details}
ARTIFACT.write_text(json.dumps(result,indent=2))
print('PREREQUISITES',json.dumps(result['prerequisites']),flush=True)
print('DIRECT_VERIFIER',json.dumps(result['direct_verifier']),flush=True)

async def replay_dag():
    from cloudra.base.session_class import Session
    from cloudra.infra.config import get_config
    from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
    from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
    from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
    from tests.dag_identity import call_dag_tool, make_coordinator
    get_config().data_dir=WORK/'runtime'
    os.environ['CLOUDRA_DB_SYNC_ON_LOOP']='raise'
    project_id='e1-native-replay'
    agent=make_coordinator(project_id,workspace_dir=str(WORKSPACE))
    session=Session(id='e1-replay',path=str(WORK/'session.json'))
    source_name='Reactant complex (F- ... HCH2CH2Cl)'
    target_name='Ethylene + HF + Cl- (separated products)'
    proposal=await call_dag_tool(DagProposeMechanism,agent,session,
        rationale='Read-only replay of packaged native E1 evidence; approvals and skipped status are not restored.',
        species=[{'name':source_name,'smiles':source_smiles},{'name':target_name,'smiles':target_smiles}],
        steps=[{'name':arguments['step_name'],'from':source_name,'to':target_name}])
    result['dag_replay']={'reconstructed_graph':True,'original_approval_state_restored':False,
                          'proposal':proposal.model_dump(mode='json'),'species_submissions':[]}
    assert proposal.is_success,proposal
    for name,relative in [(source_name,'calc/rc2.log'),(target_name,'calc/endpoint_fwd5.log')]:
        out=await call_dag_tool(DagSubmitSpeciesEvidence,agent,session,species_name=name,opt_file=relative)
        result['dag_replay']['species_submissions'].append(out.model_dump(mode='json'))
        print('DAG_SPECIES',name,json.dumps(out.result.get('scientific_checks',{})),flush=True)
        assert out.is_success,out
    out=await call_dag_tool(DagSubmitStepEvidence,agent,session,**arguments)
    result['dag_replay']['step_submission']=out.model_dump(mode='json')
    print('DAG_STEP',out.is_success,json.dumps(out.result.get('scientific_checks',{})),flush=True)
    assert out.is_success,out
asyncio.run(replay_dag())
result['original_source_hashes_unchanged']=digest_tree(SOURCE)==original_hashes
result['copied_calc_hashes_unchanged']=all(hashlib.sha256((WORKSPACE/name).read_bytes()).hexdigest()==digest
    for name,digest in original_hashes.items() if name.startswith('calc/'))
ARTIFACT.write_text(json.dumps(result,indent=2))
print('HASHES_UNCHANGED',result['original_source_hashes_unchanged'],result['copied_calc_hashes_unchanged'],flush=True)
print('ARTIFACT',ARTIFACT,flush=True)
