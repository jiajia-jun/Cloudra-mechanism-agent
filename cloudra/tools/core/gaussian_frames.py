"""Gaussian 日志关键帧提取：任务类型识别 + 逐帧结构/能量/频率导出。

让 agent 不必手写正则啃 Gaussian 日志：

- opt / freq / scan 走 cclib（scfenergies / atomcoords / vibfreqs / optdone /
  scanenergies / scanparm / scancoords），支持良好；
- IRC 为自写解析器：cclib 1.8.x 只对 IRC 做收敛记账（optstatus），不提取反应
  坐标与路径点，且其 scfenergies/atomcoords 会混入 predictor-corrector 微迭代
  的中间点，因此 IRC 分支完全不使用 cclib 的逐点序列。

本模块为纯函数，不依赖 cloudra 的 Tool 体系；cclib / numpy 在函数内惰性导入。
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field

EV_PER_HARTREE = 27.211386245988


@dataclass
class FrameRecord:
    """一个关键帧：优化步 / 扫描点 / IRC 路径点 / 单点结构。"""

    frame: int
    path_number: int | None = None          # IRC 路径号（1=正向 2=反向），其余任务为 None
    reaction_coordinate: float | None = None  # IRC 反应坐标 / 扫描参数值
    scf_energy_hartree: float | None = None
    frequencies_cm: list[float] = field(default_factory=list)  # 有符号，负值=虚频
    xyz: str = ""                            # 标准 XYZ 块（原子数行+注释行+坐标行）
    converged: bool | None = None            # 末帧/端点帧的收敛标记，其余为 None


# ---------------------------------------------------------------------------
# 任务类型识别
# ---------------------------------------------------------------------------

def _read_text(log_path: str) -> str:
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _collect_route_card(text: str) -> str:
    """收集日志中回显的路由行（` #` 开头，可能跨行缠绕），拼接为小写字符串。

    Gaussian 的路由回显块中每行以 " #" 开头；跨行缠绕多为行写满后从 token
    中间断开（如 "stepsize=10,m" / "axpoint=100"），因此同一块内直接无空格
    拼接。IRC 日志里的 " # OF POINTS ALONG THE PATH" 等计数行不是路由，剔除。
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.upper().startswith("# OF"):
            current.append(stripped[1:].strip())
        else:
            if current:
                blocks.append("".join(current))
                current = []
    if current:
        blocks.append("".join(current))
    return " ".join(blocks).lower()


def detect_job_types(log_path: str) -> set[str]:
    """识别 Gaussian 日志的任务类型，返回 {"opt","ts","freq","scan","irc","sp"} 的子集。

    依据路由卡（` #` 回显行）+ 结构标记兜底（IRC 的 "IRC-IRC-IRC" 块与
    "Summary of reaction path following"，扫描的 "Summary of Optimized
    Potential Surface Scan" 等）。`ts` 只在路由中出现 opt=(ts...) / opt=ts 时给出。

    限制：Link1 多步任务不拆分 section，按整文件取合集（v1）。
    """
    return detect_job_types_from_text(_read_text(log_path))


def detect_job_types_from_text(text: str) -> set[str]:
    """detect_job_types 的文本变体：调用方已读过日志时避免重复 IO。"""
    route = _collect_route_card(text)
    jobs: set[str] = set()

    if (
        re.search(r"\birc\b|irc\s*[=(]", route)
        or "IRC-IRC-IRC" in text
        or "Summary of reaction path following" in text
    ):
        jobs.add("irc")
    if re.search(r"\bscan\b", route) or "Summary of Optimized Potential Surface Scan" in text:
        jobs.add("scan")
    if re.search(r"\bopt\b|opt\s*=", route) or "Optimization completed" in text:
        jobs.add("opt")
    if re.search(r"opt\s*=\s*\(?\s*ts\b", route) or re.search(r"opt\s*=\s*\([^)]*\bts\b", route):
        jobs.add("ts")
    if re.search(r"\bfreq", route) or "Harmonic frequencies" in text:
        jobs.add("freq")
    if not jobs & {"irc", "scan", "opt", "ts"}:
        # 无几何移动的任务（含 freq-only）视为单点
        jobs.add("sp")
    return jobs


# ---------------------------------------------------------------------------
# XYZ 生成
# ---------------------------------------------------------------------------

def _coords_to_xyz(atomnos, coords, comment: str = "") -> str:
    """atomnos + 坐标（Angstrom）生成标准 XYZ 块。"""
    from cclib.parser.utils import PeriodicTable

    pt = PeriodicTable()
    lines = [str(len(atomnos)), comment]
    for z, (x, y, zc) in zip(atomnos, coords, strict=True):
        lines.append(f"{pt.element[int(z)]:<2} {x:>15.8f} {y:>15.8f} {zc:>15.8f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 简正模式位移与标准取向（文本权威，不依赖 cclib）
# ---------------------------------------------------------------------------

_FREQ_LINE_RE = re.compile(r"Frequencies --\s+(.*)")
_ATOM_DISP_HEADER_RE = re.compile(r"^\s*Atom\s+AN\s+X\s+Y\s+Z", re.MULTILINE)
# 公开别名：跨模块复用（如 ts_guess 的频率文本回退）应走公开名，私有名可能重构
FREQ_LINE_RE = _FREQ_LINE_RE


def vibdisps_from_text(text: str, n_freqs: int):
    """从 Gaussian 频率块解析简正模式位移，返回 shape (n_modes, n_atoms, 3) 或 None。

    按 Frequencies 行分块；每块最多 3 个模式，后接 Atom AN 位移表。块数不足
    n_freqs 或任一块缺位移表时返回 None（调用方保持"缺位移"语义）。
    """
    import numpy as np

    freq_matches = list(_FREQ_LINE_RE.finditer(text))
    if not freq_matches or n_freqs <= 0:
        return None

    mode_chunks: list[list[list[list[float]]]] = []
    for idx, match in enumerate(freq_matches):
        block_freqs = []
        for tok in match.group(1).split():
            try:
                block_freqs.append(float(tok))
            except ValueError:
                break
        if not block_freqs:
            continue
        start = match.end()
        end = freq_matches[idx + 1].start() if idx + 1 < len(freq_matches) else len(text)
        block = text[start:end]
        header = _ATOM_DISP_HEADER_RE.search(block)
        if header is None:
            return None
        rows: list[list[list[float]]] = []
        for line in block[header.end():].splitlines():
            stripped = line.strip()
            if not stripped:
                if rows:
                    break
                continue
            parts = stripped.split()
            if len(parts) < 2 + 3 * len(block_freqs):
                if rows:
                    break
                continue
            try:
                coords = [float(x) for x in parts[2:2 + 3 * len(block_freqs)]]
            except ValueError:
                if rows:
                    break
                continue
            atom_modes = [
                coords[3 * m: 3 * m + 3] for m in range(len(block_freqs))
            ]
            rows.append(atom_modes)
        if not rows:
            return None
        # rows: natoms × nmodes_in_block × 3  → 转成 per-mode
        per_mode = []
        for m in range(len(block_freqs)):
            per_mode.append([rows[a][m] for a in range(len(rows))])
        mode_chunks.append(per_mode)

    flat_modes: list[list[list[float]]] = []
    for chunk in mode_chunks:
        flat_modes.extend(chunk)
    if len(flat_modes) < n_freqs:
        return None
    arr = np.asarray(flat_modes[:n_freqs], dtype=float)
    if arr.ndim != 3 or arr.shape[2] != 3:
        return None
    return arr


def std_orientation_frames(text: str) -> list[list[tuple[int, float, float, float]]]:
    """解析所有 "Standard orientation:" 坐标块，返回 [(atomno, x, y, z), ...] 列表的列表。"""
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "Standard orientation:" in lines[i]:
            j = i + 1
            dash = 0
            rows: list[tuple[int, float, float, float]] = []
            while j < len(lines):
                s = lines[j].strip()
                if s and set(s) == {"-"}:
                    dash += 1
                    j += 1
                    if dash == 3:
                        break
                    continue
                if dash == 2:
                    parts = s.split()
                    if len(parts) >= 6:
                        rows.append((int(parts[1]), float(parts[3]), float(parts[4]), float(parts[5])))
                j += 1
            if rows:
                blocks.append(rows)
            i = j
        else:
            i += 1
    return blocks


# ---------------------------------------------------------------------------
# IRC 解析（自写，不走 cclib 逐点序列）
# ---------------------------------------------------------------------------

_POINT_HEADER_RE = re.compile(r"Point Number:\s*(\d+)\s+Path Number:\s*(\d+)")
_NET_RX_RE = re.compile(r"NET REACTION COORDINATE UP TO THIS POINT =\s*(-?[\d.]+)")
_TS_ENERGY_RE = re.compile(r"Energies reported relative to the TS energy of\s*(-?[\d.]+)")
_SUMMARY_TABLE_RE = re.compile(
    r"Summary of reaction path following\s*\n\s*-+\s*\n\s*Energy\s+RxCoord\s*\n(.*?)\n\s*-+",
    re.S,
)


def _is_dash_line(line: str) -> bool:
    s = line.strip()
    return len(s) > 3 and set(s) == {"-"}


def _parse_coord_block_after(lines: list[str], start: int, has_type_col: bool):
    """从 lines[start] 之后第一个双虚线表的坐标区解析 (atomno, x, y, z) 列表。"""
    dash_seen = 0
    rows = []
    for i in range(start, len(lines)):
        line = lines[i]
        if _is_dash_line(line):
            dash_seen += 1
            if dash_seen == 3:
                break
            continue
        if dash_seen == 2:
            parts = line.split()
            if has_type_col and len(parts) >= 6:
                rows.append((int(parts[1]), float(parts[3]), float(parts[4]), float(parts[5])))
            elif not has_type_col and len(parts) == 5:
                rows.append((int(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])))
    return rows or None


def _parse_current_structure(segment: str):
    """解析点段内 "CURRENT STRUCTURE" 的 Cartesian 坐标块（无 Type 列，5 列）。"""
    lines = segment.splitlines()
    for i, line in enumerate(lines):
        if "CURRENT STRUCTURE" in line:
            return _parse_coord_block_after(lines, i + 1, has_type_col=False)
    return None


def _parse_last_input_orientation(region: str):
    """解析文本区域内最后一个 "Input orientation:" 坐标块（含 Type 列，6 列）。"""
    lines = region.splitlines()
    last_idx = None
    for i, line in enumerate(lines):
        if "Input orientation:" in line:
            last_idx = i
    if last_idx is None:
        return None
    return _parse_coord_block_after(lines, last_idx + 1, has_type_col=True)


def _parse_irc_summary_table(text: str):
    """解析结尾汇总表，返回 (ts_energy_hartree, [(energy_rel, rx_coord), ...])。

    表中能量为相对 TS 能量的差值，行按反应坐标从负到正排列（TS 行为 rx=0）。
    """
    m_ts = _TS_ENERGY_RE.search(text)
    m_tab = _SUMMARY_TABLE_RE.search(text)
    if not m_ts or not m_tab:
        raise ValueError("IRC 日志缺少 'Summary of reaction path following' 汇总表，无法提取反应坐标与能量。")
    rows = []
    for line in m_tab.group(1).splitlines():
        parts = line.split()
        if len(parts) == 3:
            rows.append((float(parts[1]), float(parts[2])))
    if not rows:
        raise ValueError("IRC 汇总表为空。")
    return float(m_ts.group(1)), rows


def _irc_direction_converged(text: str, direction: str) -> bool:
    """判断 IRC 某个方向（FORWARD/REVERSE）是否收敛到极小点。

    Gaussian 在路径自然终止于 PES 极小点时直接打印
    "Calculation of XXX path complete."；若因步数耗尽终止则先打印
    "Maximum number of steps reached."。cclib 的 optstatus 对 IRC 点一律记为
    DONE，无法区分这两种情形，故以文本标记为准。
    """
    idx = text.find(f"Calculation of {direction} path complete.")
    if idx < 0:
        return False
    window = text[max(0, idx - 500):idx]
    return "Maximum number of steps reached" not in window


def _parse_irc(text: str):
    """解析 IRC 日志，返回 (frames, meta)。

    - 反应坐标与能量：结尾 "Summary of reaction path following" 汇总表
      （能量 = TS 能量 + 相对能量）；
    - 坐标：每个 "Point Number: N / Path Number: M" 标记后的 CURRENT STRUCTURE
      坐标块（即 corrector 收敛后的该点结构；点段内的 Input orientation 是
      下一点的 predictor 猜测结构，不采用）。Point 0（TS）无 CURRENT STRUCTURE
      块时，回退到该标记之前最后一个 Input orientation 块，仍无则 xyz 留空；
    - 汇总表按 rx 从负到正排列，通过各点 "NET REACTION COORDINATE"（到 TS 的
      距离，恒正）与 |rx| 匹配，确定正/负侧对应哪个 Path Number；
    - 输出帧按反应坐标升序排列（反向端点 → TS → 正向端点）。
    """
    ts_energy, rows = _parse_irc_summary_table(text)

    headers = list(_POINT_HEADER_RE.finditer(text))
    if not headers:
        raise ValueError("IRC 日志中未找到 'Point Number: N / Path Number: M' 标记。")

    # 每个点段：从当前标记到下一标记
    points: dict[int, list[dict]] = {1: [], 2: []}
    for i, m in enumerate(headers):
        point_no, path_no = int(m.group(1)), int(m.group(2))
        seg_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        segment = text[m.end():seg_end]
        coords = _parse_current_structure(segment)
        if point_no == 0 and coords is None:
            # TS 起始点：尝试取标记之前（初始结构 SCF）的最后一个 Input orientation
            coords = _parse_last_input_orientation(text[:m.start()])
        m_net = _NET_RX_RE.search(segment)
        points.setdefault(path_no, []).append({
            "point": point_no,
            "path": path_no,
            "net_rx": float(m_net.group(1)) if m_net else (0.0 if point_no == 0 else None),
            "coords": coords,
        })

    # 拆分汇总表：rx=0 为 TS 行，负/正两侧按到 TS 距离升序
    neg_rows = sorted((r for r in rows if r[1] < 0), key=lambda r: -r[1])
    pos_rows = sorted((r for r in rows if r[1] > 0), key=lambda r: r[1])
    ts_rows = [r for r in rows if r[1] == 0]

    def _mismatch(pts, side_rows):
        n = min(len(pts), len(side_rows))
        return sum(
            abs((pts[i]["net_rx"] or 0.0) - abs(side_rows[i][1]))
            for i in range(n)
        )

    # Path 1 的点列与负/正侧各匹配一次，取总误差小的归属
    pts1 = sorted(points.get(1, []), key=lambda p: p["point"])
    pts2 = sorted(points.get(2, []), key=lambda p: p["point"])
    pts1 = [p for p in pts1 if p["point"] > 0]
    pts2 = [p for p in pts2 if p["point"] > 0]
    score_a = _mismatch(pts1, pos_rows) + _mismatch(pts2, neg_rows)
    score_b = _mismatch(pts1, neg_rows) + _mismatch(pts2, pos_rows)
    path_rows = {1: pos_rows, 2: neg_rows} if score_a <= score_b else {1: neg_rows, 2: pos_rows}

    conv = {
        1: _irc_direction_converged(text, "FORWARD"),
        2: _irc_direction_converged(text, "REVERSE"),
    }

    def _make_frame(frame_idx, path_no, pt, row):
        energy_rel, rx = row
        energy = ts_energy + energy_rel
        coords = pt["coords"] if pt else None
        atomnos = [c[0] for c in coords] if coords else None
        xyz = ""
        if coords:
            xyz = _coords_to_xyz(
                atomnos,
                [c[1:] for c in coords],
                comment=f"irc point={pt['point']} path={path_no} rx={rx:.5f} E={energy:.8f} Eh",
            )
        return FrameRecord(
            frame=frame_idx,
            path_number=path_no,
            reaction_coordinate=rx,
            scf_energy_hartree=energy,
            xyz=xyz,
            converged=None,
        )

    frames: list[FrameRecord] = []
    idx = 0
    # 反向侧（rx 更负）：点号从大到小
    for path_no in (1, 2):
        side = path_rows[path_no]
        if side and side[0][1] < 0:
            pts = pts1 if path_no == 1 else pts2
            for i in range(len(side) - 1, -1, -1):
                pt = pts[i] if i < len(pts) else None
                fr = _make_frame(idx, path_no, pt or {"point": i + 1, "coords": None}, side[i])
                if i == len(side) - 1:
                    fr.converged = conv[path_no]  # 该方向端点
                frames.append(fr)
                idx += 1
    # TS
    ts_pt = next((p for p in points.get(1, []) if p["point"] == 0), None)
    ts_row = ts_rows[0] if ts_rows else (0.0, 0.0)
    frames.append(_make_frame(idx, ts_pt["path"] if ts_pt else 1,
                              ts_pt or {"point": 0, "coords": None}, ts_row))
    idx += 1
    # 正向侧（rx 更正）：点号从小到大
    for path_no in (1, 2):
        side = path_rows[path_no]
        if side and side[0][1] > 0:
            pts = pts1 if path_no == 1 else pts2
            for i in range(len(side)):
                pt = pts[i] if i < len(pts) else None
                fr = _make_frame(idx, path_no, pt or {"point": i + 1, "coords": None}, side[i])
                if i == len(side) - 1:
                    fr.converged = conv[path_no]
                frames.append(fr)
                idx += 1

    rx_values = [f.reaction_coordinate for f in frames if f.reaction_coordinate is not None]
    meta = {
        "ts_energy_hartree": ts_energy,
        "num_points_forward": len(pts1),
        "num_points_backward": len(pts2),
        "rx_coord_range": (min(rx_values), max(rx_values)) if rx_values else None,
        "endpoint_energies_hartree": (
            frames[0].scf_energy_hartree,
            frames[-1].scf_energy_hartree,
        ) if frames else None,
        "forward_converged": conv[1],
        "backward_converged": conv[2],
    }
    return frames, meta


def extract_irc(log_path: str):
    """解析 IRC 日志，返回 (list[FrameRecord], meta dict)。供 log_parser 汇总用。"""
    return extract_irc_from_text(_read_text(log_path))


def extract_irc_from_text(text: str):
    """extract_irc 的文本变体：调用方已读过日志时避免重复 IO。"""
    return _parse_irc(text)


# ---------------------------------------------------------------------------
# cclib 分支：scan / opt / freq / sp
# ---------------------------------------------------------------------------

def _ccread(log_path: str):
    return _ccread_from_text(_read_text(log_path), source_desc=log_path)


def _ccread_from_text(text: str, source_desc: str = "<in-memory log text>"):
    """_ccread 的文本变体：调用方已读过日志时避免重复 IO（cclib 吃 StringIO）。"""
    import io

    import cclib

    try:
        data = cclib.io.ccread(io.StringIO(text))
    except IndexError as exc:
        # cclib 内部对截断/畸形日志会裸抛 "list index out of range"——翻译成
        # 有语义的解析失败，调用方（format_converter 等）才能给出可读指引
        raise ValueError(
            f"日志解析器内部索引越界（疑似截断或损坏的计算日志）: {source_desc}"
        ) from exc
    if data is None:
        raise ValueError(f"cclib 未能解析日志: {source_desc}")
    return data


def _as_float_list(values) -> list[float]:
    import numpy as np

    return [float(v) for v in np.asarray(list(values), dtype=float)]


def _extract_scan_frames(log_text: str) -> list[FrameRecord]:
    data = _ccread_from_text(log_text)
    energies = getattr(data, "scanenergies", None)
    parm = getattr(data, "scanparm", None)
    if energies is None or parm is None or len(parm) == 0:
        return []
    energies_ev = _as_float_list(energies)
    parm_values = _as_float_list(parm[0])  # 多参数扫描 v1 只取第一个参数
    coords = getattr(data, "scancoords", None)
    atomnos = getattr(data, "atomnos", None)
    n = len(energies_ev)
    has_coords = coords is not None and atomnos is not None and len(coords) == n

    frames = []
    for i in range(n):
        rx = parm_values[i] if i < len(parm_values) else None
        xyz = ""
        if has_coords:
            xyz = _coords_to_xyz(atomnos, coords[i], comment=f"scan point={i} parm={rx}")
        frames.append(FrameRecord(
            frame=i,
            reaction_coordinate=rx,
            scf_energy_hartree=energies_ev[i] / EV_PER_HARTREE,
            xyz=xyz,
        ))
    return frames


def _opt_converged(data) -> bool | None:
    optdone = getattr(data, "optdone", None)
    if isinstance(optdone, bool):
        return optdone
    if optdone:  # 部分 cclib 版本中 optdone 是收敛步索引列表
        return True
    return None


def _get_vibfreqs(data) -> list[float]:
    vibfreqs = getattr(data, "vibfreqs", None)
    if vibfreqs is None or len(vibfreqs) == 0:
        return []
    return _as_float_list(vibfreqs)


def _extract_opt_frames(log_text: str) -> list[FrameRecord]:
    data = _ccread_from_text(log_text)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if energies is None or atomcoords is None or atomnos is None:
        return []
    energies_ev = _as_float_list(energies)
    n = min(len(energies_ev), len(atomcoords))
    converged = _opt_converged(data)
    freqs = _get_vibfreqs(data)

    frames = []
    for i in range(n):
        is_last = i == n - 1
        frames.append(FrameRecord(
            frame=i,
            scf_energy_hartree=energies_ev[i] / EV_PER_HARTREE,
            frequencies_cm=freqs if (is_last and freqs) else [],
            xyz=_coords_to_xyz(atomnos, atomcoords[i], comment=f"opt step={i}"),
            converged=converged if is_last else None,
        ))
    return frames


def _extract_sp_frames(log_text: str) -> list[FrameRecord]:
    data = _ccread_from_text(log_text)
    energies = getattr(data, "scfenergies", None)
    atomcoords = getattr(data, "atomcoords", None)
    atomnos = getattr(data, "atomnos", None)
    if atomcoords is None or atomnos is None or len(atomcoords) == 0:
        return []
    energy_hartree = None
    if energies is not None and len(energies) > 0:
        energy_hartree = _as_float_list(energies)[-1] / EV_PER_HARTREE
    return [FrameRecord(
        frame=0,
        scf_energy_hartree=energy_hartree,
        frequencies_cm=_get_vibfreqs(data),
        xyz=_coords_to_xyz(atomnos, atomcoords[-1], comment="single point"),
    )]


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

def extract_frames(log_path: str) -> list[FrameRecord]:
    """按识别到的任务类型提取关键帧。无法识别的日志返回空列表。"""
    return extract_frames_from_text(_read_text(log_path))


def extract_frames_from_text(text: str) -> list[FrameRecord]:
    """extract_frames 的文本变体：调用方已读过日志时避免重复 IO。"""
    jobs = detect_job_types_from_text(text)
    if "irc" in jobs:
        frames, _meta = _parse_irc(text)
        return frames
    if "scan" in jobs:
        return _extract_scan_frames(text)
    if "opt" in jobs or "ts" in jobs:
        return _extract_opt_frames(text)
    # freq / sp：单帧
    return _extract_sp_frames(text)


def _fmt_float(value: float, digits: int = 12) -> str:
    return f"{value:.{digits}g}"


def frames_to_csv(frames: list[FrameRecord], output_path: str) -> str:
    """将关键帧写为 CSV（xyz 为多行字段，靠 csv 引号机制，pandas/DictReader 可读）。"""
    columns = [
        "frame", "path_number", "reaction_coordinate",
        "scf_energy_hartree", "scf_energy_ev", "frequencies_cm", "xyz",
    ]
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for fr in frames:
            hartree = fr.scf_energy_hartree
            writer.writerow({
                "frame": fr.frame,
                "path_number": "" if fr.path_number is None else fr.path_number,
                "reaction_coordinate": "" if fr.reaction_coordinate is None else _fmt_float(fr.reaction_coordinate),
                "scf_energy_hartree": "" if hartree is None else _fmt_float(hartree),
                "scf_energy_ev": "" if hartree is None else _fmt_float(hartree * EV_PER_HARTREE),
                "frequencies_cm": ";".join(_fmt_float(v) for v in fr.frequencies_cm),
                "xyz": fr.xyz,
            })
    return output_path
