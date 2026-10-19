"""Read-only E1 native Gaussian predictor/corrector lineage audit.

Uses repository native_input_geometry for .gjf files and native Gaussian parsers.
Never treats README helpers or invented coordinate tolerances as authority.
"""
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
import json

import numpy as np

from cloudra.tools.core import gaussian_frames as gf
from cloudra.tools.core import irc_evidence as ie
from cloudra.tools.core.calculation_intent import native_input_geometry
from cloudra.tools.core.irc_path import align_atom_order, parse_xyz, same_geometry

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('calc_dir', type=Path, help='Absolute path to the extracted E1 calc directory')
args = parser.parse_args()
if not args.calc_dir.is_absolute():
    parser.error('calc_dir must be absolute because the probe isolates its working directory')
base = args.calc_dir
text = (base/'irc3.log').read_text()
headers = list(gf._POINT_HEADER_RE.finditer(text))
def line_at(offset):
    return text.count('\n', 0, offset)+1

def rows_geo(rows):
    return parse_xyz(gf._coords_to_xyz([row[0] for row in rows], [row[1:] for row in rows]))

def gjf_geo(path):
    rows = native_input_geometry(path.read_text(), engine='gaussian')
    return [row[0] for row in rows], [row[1] for row in rows]

def first_orientation(source):
    lines=source.splitlines()
    i=next(i for i,line in enumerate(lines) if 'Input orientation:' in line or 'Standard orientation:' in line)
    return rows_geo(gf._parse_coord_block_after(lines,i+1,has_type_col=True))

def aligned_max(ref, mob):
    ref=np.array(ref,dtype=float)
    mob=np.array(mob,dtype=float)
    ref=ref-ref.mean(axis=0)
    mob=mob-mob.mean(axis=0)
    u,_,vt=np.linalg.svd(mob.T@ref)
    if np.linalg.det(u@vt)<0:
        u[:,-1]*=-1
    residual=np.linalg.norm(mob@(u@vt)-ref,axis=1)
    return float(np.max(residual))

def metrics(reference,mobile):
    ref,mob=np.array(reference[1]),np.array(mobile[1])
    result=dict(symbol_order_equal=list(reference[0])==list(mobile[0]),
        raw_max_component_A=float(np.max(np.abs(ref-mob))),
        proper_aligned_native_order_max_atom_residual_A=aligned_max(ref,mob),
        max_pair_distance_difference_A=float(np.max(np.abs(np.linalg.norm(ref[:,None]-ref[None,:],axis=-1)-np.linalg.norm(mob[:,None]-mob[None,:],axis=-1)))),
        same_geometry=bool(same_geometry(reference,mobile)))
    alignment=align_atom_order(*reference,*mobile)
    if alignment:
        perm=list(map(int,alignment[0]))
        result['repository_align_perm']=perm
        result['proper_aligned_repository_perm_max_atom_residual_A']=aligned_max(ref,mob[perm])
    return result

frames,meta=gf.extract_irc_from_text(text)
outer_frames={'reverse':frames[0],'forward':frames[-1]}
report=dict(source=str(base/'irc3.log'), strict_tolerance_A=float(np.sqrt(3)*1e-6),
    native_metadata=meta, endpoints={})
for side,point,path_no in [('reverse',39,2),('forward',141,1)]:
    index=next(i for i,h in enumerate(headers) if tuple(map(int,h.groups()))==(point,path_no))
    header=headers[index]
    end=headers[index+1].start() if index+1<len(headers) else len(text)
    segment=text[header.end():end]
    current=rows_geo(gf._parse_current_structure(segment))
    before=rows_geo(gf._parse_last_input_orientation(text[:header.start()]))
    prior_input_offset=text.rfind('Input orientation:',0,header.start())
    next_input_offset=text.find('Input orientation:',header.end())
    after=rows_geo(gf._parse_last_input_orientation(text[next_input_offset:text.find('Distance matrix',next_input_offset)]))
    start_input=gjf_geo(base/f'endpoint_{"rev" if side=="reverse" else "fwd"}5.gjf')
    opt_log=base/f'endpoint_{"rev" if side=="reverse" else "fwd"}5.log'
    native_opt=ie._optimization_geometries(opt_log)
    assert native_opt is not None, 'native Opt geometry extraction failed'
    opt_start=native_opt[0]
    imag,freq_final=ie.probe_log(opt_log)
    report['endpoints'][side]=dict(point=point,path=path_no,
        point_header_line=line_at(header.start()),
        input_before_header_line=line_at(prior_input_offset),
        current_structure_line=line_at(text.index('CURRENT STRUCTURE',header.end(),end)),
        first_input_after_header_line=line_at(next_input_offset),
        opt_input_vs_current=metrics(current,start_input),
        opt_input_vs_prior_input=metrics(before,start_input),
        opt_input_vs_next_input=metrics(after,start_input),
        native_opt_first_vs_gjf=metrics(start_input,opt_start),
        native_opt_first_vs_current=metrics(current,opt_start),
        extracted_irc_outer_vs_current=metrics(current,parse_xyz(outer_frames[side].xyz)),
        input_before_vs_after_rows_equal=before==after,
        native_opt_final_vs_frequency_final=metrics(native_opt[1],freq_final),
        imaginary_frequency_count=imag)

start=ie.irc_start_geometry(base/'irc3.log')
ts_imag,ts_geo=ie.probe_log(base/'ts1.log')
report['ts_to_irc_start']=dict(ts_imaginary_frequency_count=ts_imag,**metrics(ts_geo,start))
report['first_geometric_link_for_endpoint_proof']=dict(
    source_start_matches_reverse=report['endpoints']['reverse']['native_opt_first_vs_current']['same_geometry'],
    target_start_matches_forward=report['endpoints']['forward']['native_opt_first_vs_current']['same_geometry'])
out=(_AUDIT_CONTEXT / 'e1_gaussian_print_semantics_audit.json')
out.write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
print('REPORT_PATH='+str(out))
