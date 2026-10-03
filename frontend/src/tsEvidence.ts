/** Display the server's supported saddle evidence, never infer it from selection.
 * Delivery does not expose a bound frequency value or normal mode/geometry pair.
 * This status therefore makes no claim about the viewer's illustrative geometry.
 */
export function hasSaddleEvidence(edge: {
  evidence_level?: unknown;
  evidence_vetoed?: unknown;
  stages?: { kind?: unknown; status?: unknown }[];
}): boolean {
  return edge.evidence_vetoed !== true
    && ['saddle_supported', 'endpoint_supported', 'thermo_annotated'].includes(String(edge.evidence_level))
    && ['ts_opt', 'frequency'].every(kind =>
      edge.stages?.some(stage => stage.kind === kind && stage.status === 'supported'));
}
