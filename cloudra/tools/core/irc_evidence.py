"""IRC 证据几何材料组装（benchmark 自洽性与 DAG live 交付门禁共用唯一实现）。

「日志路径 → 几何材料」的探针逻辑唯一来源：

- ``probe_log``：日志的虚频数与末帧几何（TS 几何与端点验证极小值几何的
  取法；无频率块时虚频数为 None，绝不冒充 0）；
- ``irc_endpoint_geometries``：IRC 双侧端点几何，ts_guess strict 同口径——
  Gaussian 取主日志逐点帧 rx<0 / rx>0 两侧最外侧的带坐标帧，ORCA 取终点
  文件/F-B 轨迹边文件；未收敛方向取轨迹末帧作部分端点，收敛与否不做闸门；
- ``iter_direction_verdicts`` / ``verify_short_irc_direction``：组装四份
  几何后调 irc_path.prove_irc_endpoint_direction（判定唯一实现）完成
  几何方向区间证明。

缺材料 fail-loud：``verify_short_irc_direction`` 返回 ``(passed, details)``，
``passed=False`` 时 details 结构化写明缺哪份材料，绝不静默降级。details
一律英文（给模型/agent 的文本）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from cloudra.tools.core import gaussian_frames, orca_frames, qm_engine
from cloudra.tools.core.irc_path import parse_xyz, prove_irc_endpoint_direction, same_geometry


def irc_start_geometry(path):
    """Native IRC starting saddle, never a predictor or a terminal path frame."""
    engine = qm_engine.detect_qm_engine(str(path))
    try:
        if engine == 'gaussian':
            frames, _ = gaussian_frames.extract_irc(str(path))
            return next((parse_xyz(frame.xyz) for frame in frames
                         if frame.reaction_coordinate == 0.0 and frame.xyz.strip()), None)
        if engine == 'orca':
            text = Path(path).read_text(errors='replace')
            orca_frames.extract_irc_from_text(text)
            start = text.find('Intrinsic Reaction Coordinate Calculation')
            if start < 0:
                return None
            index = text.rfind('CARTESIAN COORDINATES (ANGSTROEM)', 0, start)
            return parse_xyz(orca_frames._xyz_block_at(text, index)) if index >= 0 else None
    except (ValueError, OSError):
        return None
    return None


def frames_for(path):
    """Return (frames, irc_meta). 两种解析各自隔离：opt+freq 日志没有 IRC 段
    是正常情况，不能让 extract_irc 的异常把已解析的 frames 一并丢弃。

    IRC meta 已归一化为 dict：gaussian_frames.extract_irc 返回
    (frames, meta) 二元组，orca_frames.extract_irc 直接返回 meta dict。
    """
    engine = qm_engine.detect_qm_engine(str(path))
    mod = orca_frames if engine == "orca" else gaussian_frames
    try:
        frames = mod.extract_frames(str(path))
    except Exception:
        frames = []
    try:
        raw_irc = mod.extract_irc(str(path))
    except Exception:
        raw_irc = None
    if isinstance(raw_irc, tuple):
        irc_meta = raw_irc[1] if len(raw_irc) == 2 else None
    else:
        irc_meta = raw_irc
    return frames, irc_meta


def _last_freqs(frames) -> list[float]:
    for fr in reversed(frames):
        if fr.frequencies_cm:
            return list(fr.frequencies_cm)
    return []


def freqs_for(path, frames) -> list[float]:
    """末帧频率；cclib 对 ORCA 6.1 日志裸抛 IndexError（帧为空）时回退
    文本权威 VIBRATIONAL FREQUENCIES 块（统一入口在 orca_frames）。"""
    freqs = _last_freqs(frames)
    if freqs:
        return freqs
    if qm_engine.detect_qm_engine(str(path)) == "orca":
        return orca_frames.frequencies_with_text_fallback(str(path))
    return []


def imag_freqs(freqs: list[float]) -> list[float]:
    return [f for f in freqs if f < 0]


def last_geometry(path, frames) -> Optional[tuple]:
    """末帧几何 (symbols, positions)；无坐标帧返回 None。

    cclib 对 ORCA 6.1 日志整体崩溃时帧为空——走文本权威
    CARTESIAN COORDINATES 块回退（同频率的文本回退纪律）。
    """
    geometry = None
    for fr in reversed(frames):
        if getattr(fr, "xyz", "").strip():
            geometry = parse_xyz(fr.xyz)
            break
    if geometry is None and qm_engine.detect_qm_engine(str(path)) == "orca":
        geometry = parse_xyz(orca_frames.final_xyz_with_text_fallback(str(path)))
    return geometry


def irc_frames_for(path):
    """IRC 逐点帧。Gaussian 主日志内含逐点坐标；ORCA 的逐点坐标在边文件里，
    主日志没有（端点几何走 orca_irc_endpoint_geometries 的边文件通道）。"""
    try:
        raw = gaussian_frames.extract_irc(str(path))
    except Exception:
        return []
    if isinstance(raw, tuple) and raw:
        return list(raw[0]) if raw[0] else []
    return []


def gaussian_irc_endpoints_from_frames(frames) -> Optional[tuple]:
    """ts_guess strict 同口径的 Gaussian IRC 端点：rx<0 / rx>0 两侧各自最外侧
    的带坐标帧（不要求收敛到极小值）。两侧都有可用几何才返回。"""
    valid = [fr for fr in frames if getattr(fr, "xyz", "").strip()]
    neg = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate < 0
    ]
    pos = [
        fr for fr in valid
        if fr.reaction_coordinate is not None and fr.reaction_coordinate > 0
    ]
    if not neg or not pos:
        return None
    end_a = min(neg, key=lambda fr: fr.reaction_coordinate)
    end_b = max(pos, key=lambda fr: fr.reaction_coordinate)
    geo_a = parse_xyz(end_a.xyz)
    geo_b = parse_xyz(end_b.xyz)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b


def orca_irc_endpoint_geometries(path) -> Optional[tuple]:
    """ts_guess strict 同口径的 ORCA IRC 端点：几何来自终点文件/F-B 轨迹边
    文件（未收敛方向取轨迹末帧，同样是合法的部分端点）；收敛与否不做闸门，
    方向是否成立交给几何区间证明。两侧都有可用几何才返回。

    前提是文件本身确实是 IRC 计算日志：输入文件（.inp）旁边恰好有同名
    轨迹边文件时，没有 IRC 段就没有任何"端点"可言。"""
    try:
        orca_frames.extract_irc(str(path))
    except Exception:
        return None  # 无 IRC 段（输入文件、非 IRC 作业）→ 不是 IRC 证据
    try:
        endpoints = orca_frames.extract_irc_endpoints(str(path))
    except Exception:
        return None
    xyz_a = orca_frames.read_endpoint_geometry(endpoints.get("forward", {}))
    xyz_b = orca_frames.read_endpoint_geometry(endpoints.get("backward", {}))
    if xyz_a is None or xyz_b is None:
        return None
    geo_a = parse_xyz(xyz_a)
    geo_b = parse_xyz(xyz_b)
    if geo_a is None or geo_b is None:
        return None
    return geo_a, geo_b


def _within_scan_limit(path: Path, max_scan_bytes: Optional[int]) -> bool:
    if max_scan_bytes is None:
        return True
    try:
        return path.stat().st_size <= max_scan_bytes
    except OSError:
        return False


def normal_log(path, *, max_scan_bytes=None) -> bool:
    """Native normally terminated QM evidence within the caller's read limit."""
    path = Path(path)
    if not path.is_file() or not _within_scan_limit(path, max_scan_bytes):
        return False
    engine = qm_engine.detect_qm_engine(str(path))
    parser = {'orca': orca_frames, 'gaussian': gaussian_frames}.get(engine)
    text = path.read_text(errors='replace')
    if parser is None or not parser.normal_termination(text):
        return False
    if engine == 'orca' and 'ORCA finished by error termination' in text:
        return False
    marker = 'ORCA TERMINATED NORMALLY' if engine == 'orca' else 'Normal termination of Gaussian'
    if text.count(marker) <= 1:
        return True
    # Link1/compound outputs may contain multiple native calculations. The
    # last frequency block must describe the final geometry, not an earlier
    # saddle whose frequencies survived a later optimization in the same file.
    parts = text.split(marker)
    segments = [part + marker for part in parts[:-1]]
    segments[-1] += parts[-1]
    def geometry(segment):
        if engine == 'orca':
            return parse_xyz(orca_frames.final_xyz_from_text(segment))
        blocks = gaussian_frames.std_orientation_frames(segment)
        coords = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(segment)
        return parse_xyz(gaussian_frames._coords_to_xyz(
            [row[0] for row in coords], [row[1:] for row in coords])) if coords else None
    final_geometry = geometry(segments[-1])
    for segment in reversed(segments):
        frequencies = (orca_frames.vibfreqs_from_text(segment) if engine == 'orca' else
                       any(line.strip().startswith('Frequencies --') for line in segment.splitlines()))
        if frequencies:
            return same_geometry(final_geometry, geometry(segment))
    return True


def probe_log(path, *, max_scan_bytes: Optional[int] = None) -> tuple[Optional[int], Optional[tuple]]:
    """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。

    只解析 gaussian/orca 日志（内容嗅探，不超过 max_scan_bytes——None 表示
    不设上限，与 ts_guess strict 同；benchmark 侧传 MAX_SCAN_BYTES）。"""
    p = Path(path)
    if not _within_scan_limit(p, max_scan_bytes):
        return None, None
    if not normal_log(p, max_scan_bytes=max_scan_bytes):
        return None, None
    frames, _irc_meta = frames_for(p)
    freqs = freqs_for(p, frames)
    n_imag = len(imag_freqs(freqs)) if freqs else None
    return n_imag, last_geometry(p, frames)


def irc_endpoint_geometries(path, *, max_scan_bytes: Optional[int] = None) -> Optional[tuple]:
    """双侧 IRC 端点几何 ((symbols, positions) × 2)，ts_guess strict 口径。

    引擎非 gaussian/orca、超尺寸上限或任一侧几何不可得时返回 None。"""
    p = Path(path)
    if not _within_scan_limit(p, max_scan_bytes):
        return None
    engine = qm_engine.detect_qm_engine(str(p))
    if engine == "gaussian":
        return gaussian_irc_endpoints_from_frames(irc_frames_for(p))
    if engine == "orca":
        return orca_irc_endpoint_geometries(p)
    return None


def iter_direction_verdicts(
    irc_ends: tuple,
    ts_geometries: Sequence[tuple],
    from_geometries: Sequence[tuple],
    to_geometries: Sequence[tuple],
    *,
    charge: int = 0,
):
    """按确定性顺序（TS → from → to）对全部材料组合逐一做方向区间证明，
    逐个产出 verdict（生成器，调用方 any()/遍历即短回路）。

    原子序无关：每组几何经 align_atom_order 重排进 TS 坐标序（距离指纹 +
    Hungarian，元素多重集不符的组合判 undecidable）——agent 用不同原子序
    重优化的端点极小值不再被误拒。"""
    (syms_a, pos_a), (syms_b, pos_b) = irc_ends
    for ts_syms, ts_pos in ts_geometries:
        for from_geo in from_geometries:
            for to_geo in to_geometries:
                yield prove_irc_endpoint_direction(
                    ts_syms, ts_pos,
                    (syms_a, pos_a), (syms_b, pos_b),
                    from_geo, to_geo, [], charge,
                )


def _usable_ts_geometries(ts_logs, *, max_scan_bytes, details: list[str]) -> list[tuple]:
    geometries = []
    for path in ts_logs:
        n_imag, geometry = probe_log(path, max_scan_bytes=max_scan_bytes)
        if n_imag == 1 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"TS candidate {path} is not usable: a first-order saddle log "
                f"(exactly one imaginary frequency) with a final geometry is "
                f"required; got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries


def _usable_minimum_geometries(logs, *, side: str, max_scan_bytes, details: list[str]) -> list[tuple]:
    geometries = []
    for path in logs:
        n_imag, geometry = probe_log(path, max_scan_bytes=max_scan_bytes)
        if n_imag == 0 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"{side} candidate {path} is not usable: a verified minimum log "
                f"(zero imaginary frequencies) with a final geometry is required; "
                f"got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries


def verify_short_irc_direction(
    irc_log,
    ts_logs: Sequence,
    endpoint_a_logs: Sequence,
    endpoint_b_logs: Sequence,
    *,
    charge: int = 0,
    max_scan_bytes: Optional[int] = None,
) -> tuple[bool, list[str]]:
    """给定 short_irc 日志与材料日志候选，完成几何方向区间证明。

    材料：IRC 双侧端点几何（irc_log）+ TS 几何（ts_logs 中任一 n_imag==1
    且带末帧几何的日志）+ 两侧端点验证极小值几何（endpoint_a_logs /
    endpoint_b_logs 中任一 n_imag==0 且带末帧几何的日志；endpoint_a 是
    TARGET/产物侧，endpoint_b 是 SOURCE/反应物侧——仅用于 details 文案，
    判定自身对两侧做 direct/swapped 无序配对）。

    返回 (passed, details)：passed=False 时 details 结构化写明缺哪份材料
    或证明为何不成立（缺 TS/端点材料 ⇒ 引导先补对应阶段的绑定证据）。
    """
    details: list[str] = []
    ends = irc_endpoint_geometries(irc_log, max_scan_bytes=max_scan_bytes)
    if ends is None:
        return False, [
            f"the IRC log {irc_log} does not yield usable endpoint geometries on "
            "both sides (Gaussian: outermost coordinated frames on the rx<0 and "
            "rx>0 sides; ORCA: endpoint files or outermost F/B trajectory frames — "
            "an unconverged direction's last frame is a legitimate partial "
            "endpoint); bind the parser output of a finished IRC job log"
        ]
    ts_geometries = _usable_ts_geometries(
        ts_logs, max_scan_bytes=max_scan_bytes, details=details
    )
    anchor = irc_start_geometry(irc_log)
    ts_geometries = [geo for geo in ts_geometries if same_geometry(geo, anchor)]
    if not ts_geometries:
        details.append('IRC starting saddle is missing or differs from the submitted TS geometry; submit evidence from the same TS calculation geometry.')
    from_geometries = _usable_minimum_geometries(
        endpoint_b_logs, side="endpoint_b (SOURCE/reactant side)",
        max_scan_bytes=max_scan_bytes, details=details,
    )
    to_geometries = _usable_minimum_geometries(
        endpoint_a_logs, side="endpoint_a (TARGET/product side)",
        max_scan_bytes=max_scan_bytes, details=details,
    )
    if not ts_geometries:
        details.append(
            "missing TS material: bind the step's ts_opt/frequency stage evidence "
            "first (a normally terminated first-order saddle log with a final geometry)"
        )
    if not from_geometries:
        details.append(
            "missing endpoint_b material (SOURCE/reactant side): bind endpoint_b "
            "evidence or the source species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not to_geometries:
        details.append(
            "missing endpoint_a material (TARGET/product side): bind endpoint_a "
            "evidence or the target species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not (ts_geometries and from_geometries and to_geometries):
        return False, details
    last_verdict: Optional[dict] = None
    for verdict in iter_direction_verdicts(
        ends, ts_geometries, from_geometries, to_geometries, charge=charge
    ):
        if verdict["is_decidable"] and verdict["is_match"]:
            return True, list(verdict.get("details") or [])
        last_verdict = verdict
    if last_verdict is not None and not last_verdict.get("is_decidable"):
        header = (
            "the direction proof is undecidable for the bound materials "
            "(atom-pair changes between the TS and the endpoint minima are too "
            "small to judge, or the geometries could not be aligned to the TS)"
        )
    else:
        header = (
            "the IRC endpoints do not lie between the TS and the verified "
            "endpoint minima (the geometric direction proof failed)"
        )
    return False, [header, *list((last_verdict or {}).get("details") or [])]


def verify_short_irc_pair(forward_log, reverse_log, ts_logs, endpoint_a_logs, endpoint_b_logs):
    """Combine explicitly submitted directional logs using the same interval proof."""
    def outer_geometry(path, direction):
        engine = qm_engine.detect_qm_engine(str(path))
        if engine == 'orca':
            orca_frames.extract_irc(str(path))
            endpoints = orca_frames.extract_irc_endpoints(str(path))
            for side in (direction, 'backward' if direction == 'forward' else 'forward'):
                xyz = orca_frames.read_endpoint_geometry(endpoints[side])
                if xyz:
                    return parse_xyz(xyz)
        elif engine == 'gaussian':
            frames = [f for f in irc_frames_for(path) if f.xyz.strip() and f.reaction_coordinate]
            preferred = [f for f in frames if (f.reaction_coordinate > 0) == (direction == 'forward')]
            candidates = preferred or frames
            if candidates:
                return parse_xyz(max(candidates, key=lambda f: abs(f.reaction_coordinate)).xyz)
        return None

    details = []
    try:
        forward = outer_geometry(forward_log, 'forward')
        reverse = outer_geometry(reverse_log, 'backward')
    except (ValueError, OSError) as exc:
        return False, [f'Directional IRC evidence could not be read: {exc}']
    if forward is None or reverse is None:
        return False, ['Both submitted directional logs must supply an outer endpoint geometry.']
    ts = _usable_ts_geometries(ts_logs, max_scan_bytes=None, details=details)
    starts = [irc_start_geometry(path) for path in (forward_log, reverse_log)]
    ts = [geo for geo in ts if all(same_geometry(geo, start) for start in starts)]
    source = _usable_minimum_geometries(endpoint_b_logs, side='SOURCE', max_scan_bytes=None, details=details)
    target = _usable_minimum_geometries(endpoint_a_logs, side='TARGET', max_scan_bytes=None, details=details)
    if not (ts and source and target):
        return False, [*details, 'Bind the TS and frequency-verified source/target minimum logs.']
    for verdict in iter_direction_verdicts((forward, reverse), ts, source, target):
        if verdict['is_decidable'] and verdict['is_match']:
            return True, list(verdict.get('details') or [])
        details.extend(verdict.get('details') or [])
    return False, ['The paired IRC endpoint interval proof failed or is undecidable.', *details]
