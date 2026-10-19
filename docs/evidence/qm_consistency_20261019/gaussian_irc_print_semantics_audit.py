"""Read-only numeric comparison of the captured HCN Gaussian IRC output."""
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

import json

import numpy as np

from cloudra.tools.core import gaussian_frames as gf
from cloudra.tools.core.irc_path import parse_xyz, same_geometry

source = (REPO_ROOT / 'tests/fixtures/gaussian/hcn_ts_irc_g16.log')
text = source.read_text()
headers = list(gf._POINT_HEADER_RE.finditer(text))
def geo(rows):
    return parse_xyz(gf._coords_to_xyz([row[0] for row in rows], [row[1:] for row in rows]))
def metrics(left, right):
    ref, mob = np.array(left[1]), np.array(right[1])
    ref_c, mob_c = ref - ref.mean(axis=0), mob - mob.mean(axis=0)
    u, _, vt = np.linalg.svd(mob_c.T @ ref_c)
    if np.linalg.det(u @ vt) < 0:
        u[:, -1] *= -1
    residual = np.linalg.norm(mob_c @ (u @ vt) - ref_c, axis=1)
    d_ref = np.linalg.norm(ref[:, None] - ref[None, :], axis=-1)
    d_mob = np.linalg.norm(mob[:, None] - mob[None, :], axis=-1)
    return dict(raw_max_component_A=float(np.max(np.abs(ref-mob))),
                proper_aligned_max_atom_residual_A=float(np.max(residual)),
                max_pair_distance_difference_A=float(np.max(np.abs(d_ref-d_mob))),
                same_geometry=same_geometry(left, right))

points = []
for index, header in enumerate(headers):
    point, path = map(int, header.groups())
    if point == 0:
        continue
    end = headers[index+1].start() if index+1 < len(headers) else len(text)
    segment = text[header.end():end]
    current = gf._parse_current_structure(segment)
    prior_input = gf._parse_last_input_orientation(text[:header.start()])
    if current is None or prior_input is None:
        continue
    prior_offset = text.rfind('Input orientation:', 0, header.start())
    current_offset = text.index('CURRENT STRUCTURE', header.end(), end)
    def line_at(offset):
        return text.count('\n', 0, offset) + 1
    points.append(dict(point=point, path=path, point_header_line=line_at(header.start()),
        prior_input_line=line_at(prior_offset), current_structure_line=line_at(current_offset),
        **metrics(geo(current), geo(prior_input))))

last_header = headers[-1]
current = gf._parse_current_structure(text[last_header.end():])
prior = gf._parse_last_input_orientation(text[:last_header.start()])
final = gf._parse_last_input_orientation(text)
frames, _ = gf.extract_irc_from_text(text)
report = dict(source=str(source), strict_tolerance_A=float(np.sqrt(3)*1e-6),
    point_count_compared=len(points), same_geometry_true_count=sum(row['same_geometry'] for row in points),
    all_points=points, final_print=dict(
        final_input_line=text.count('\n', 0, text.rfind('Input orientation:'))+1,
        final_input_equals_prior_input_rows=final == prior,
        final_input_vs_corrected_current=metrics(geo(current),geo(final)),
        native_extracted_reverse_outer_frame_equals_corrected_current=same_geometry(geo(current),parse_xyz(frames[0].xyz))))
output = (_AUDIT_CONTEXT / 'gaussian_irc_print_semantics_audit.json')
output.write_text(json.dumps(report, indent=2))
print(json.dumps({key:value for key,value in report.items() if key!='all_points'},indent=2))
print('SELECTED_POINTS=' + json.dumps([row for row in points if row['point'] in (1,10)],indent=2))
print('REPORT_PATH=' + str(output))
