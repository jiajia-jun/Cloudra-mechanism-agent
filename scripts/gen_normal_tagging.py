"""从 ideapool/reaction_candidates/normal.md 生成 Normal 档评审打标台（自包含 HTML）。

用法：.venv/bin/python scripts/gen_normal_tagging.py
产物：ideapool/reaction_candidates/normal_tagging.html（浏览器直接打开；
打标状态存 localStorage，可导出/导入 JSON，可导出正选/替补名单文本）。

池子条目变更后重跑本脚本即可重建打标台；localStorage 里的打标按条目 id 对齐，
增删条目不会串位。打标台只是一层标注 UI，不回写 normal.md——名单定稿后人工更新。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ideapool" / "reaction_candidates" / "normal.md"
OUT = ROOT / "ideapool" / "reaction_candidates" / "normal_tagging.html"

ROW_RE = re.compile(r"^\|\s*([A-Z]\d+)\s*\|")
SMILES_RE = re.compile(r"`([^`]+)`(?:（[^）]*）)?\s*[，,]\s*([+−\-]?\d+)\s*/\s*(\d+)")
VERIFY_RE = re.compile(r"\[(已核实存在|已核实|部分核实|未核实)\]")

# 循序渐进三带映射（normal.md 汇总段的权威映射，改池子时同步维护）。
BANDS: dict[str, list[str]] = {
    "N1 路线判别": "X1 X2 X3 X4 A7 O2 I1 I3 Y2 Y3 O4 O5 R3 Q2 U6 U7".split(),
    "N2 简单多步": "A1 A6 U1 R6 Q1 I4 O3 Y1 Y4 O1 H3 H4 H5".split(),
    "N3 复杂人名网络": "A2 A3 A4 A5 I2 R1 R2 R4 U2 U4 U5 H1 H2 Q3".split(),
    "待裁决": "S1 R5 U3 S2 Q4".split(),
}
# 2026-08-30 定稿名单（normal.md"定稿圈定"段为权威；此处只作打标台初始默认值）。
SUGGESTED_PICK = "A1 A2 A4 A5 A7 I1 I3 Y2 Y3 O2 O3 O4 O5 X1 X2 X3 X4 R1 R2 R3 U1 U5 U6 U7 Q2 Q3 H1 H2 H3 H5".split()
SUGGESTED_ALT: list[str] = []

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Normal 档打标台（__N__ 条候选）</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif; margin: 0; background: #0f1115; color: #d7dae0; }
  header { position: sticky; top: 0; z-index: 10; background: #161a22; border-bottom: 1px solid #2a2f3a; padding: 10px 16px; }
  header h1 { font-size: 15px; margin: 0 0 8px; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 13px; }
  .counter { padding: 2px 10px; border-radius: 10px; background: #222836; font-variant-numeric: tabular-nums; }
  .counter b { color: #7ec8ff; }
  .counter.over b { color: #ff7e7e; }
  select, input[type=search] { background: #1d2230; color: #d7dae0; border: 1px solid #333a4a; border-radius: 6px; padding: 4px 8px; font-size: 13px; }
  button { background: #1d2230; color: #d7dae0; border: 1px solid #333a4a; border-radius: 6px; padding: 4px 10px; font-size: 12.5px; cursor: pointer; }
  button:hover { border-color: #5a6580; }
  main { padding: 12px 16px 60px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { border-bottom: 1px solid #242a36; padding: 7px 8px; text-align: left; vertical-align: top; }
  th { position: sticky; top: 92px; background: #161a22; font-size: 12px; color: #8b93a5; }
  td.id { font-weight: 700; white-space: nowrap; }
  code { font-size: 11.5px; color: #9fd3a8; word-break: break-all; }
  .band { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: #222836; white-space: nowrap; }
  .tag-btns button { margin-right: 4px; opacity: 0.45; }
  .tag-btns button.on { opacity: 1; font-weight: 700; }
  .b-pick.on { background: #1d4a2c; border-color: #3a8f56; color: #9fe6b5; }
  .b-alt.on  { background: #4a3a1d; border-color: #a8823a; color: #f0d59a; }
  .b-drop.on { background: #4a1d22; border-color: #a83a46; color: #f0a3ab; }
  tr.st-pick { background: rgba(40, 120, 70, 0.10); }
  tr.st-alt  { background: rgba(150, 110, 40, 0.10); }
  tr.st-drop { opacity: 0.38; }
  .vtag { font-size: 11px; padding: 1px 6px; border-radius: 8px; white-space: nowrap; }
  .v-已核实 { background: #1d4a2c; color: #9fe6b5; }
  .v-已核实存在 { background: #1d3a4a; color: #9ad4f0; }
  .v-部分核实 { background: #4a3a1d; color: #f0d59a; }
  .v-未核实 { background: #4a1d22; color: #f0a3ab; }
  .mech, .barrier { max-width: 420px; }
  .hidden { display: none; }
  textarea#importbox { width: 100%; height: 90px; background: #1d2230; color: #d7dae0; border: 1px solid #333a4a; }
</style>
</head>
<body>
<header>
  <h1>Normal 档打标台 · __N__ 条候选 · 目标正选 30 / 替补 10（打标存 localStorage，不回写 normal.md）</h1>
  <div class="bar">
    <span class="counter" id="c-pick">正选 <b>0</b>/30</span>
    <span class="counter" id="c-alt">替补 <b>0</b>/10</span>
    <span class="counter" id="c-drop">剔除 <b>0</b></span>
    <span class="counter" id="c-todo">未定 <b>0</b></span>
    <select id="f-band"><option value="">全部带</option></select>
    <select id="f-fam"><option value="">全部族</option></select>
    <select id="f-tag">
      <option value="">全部标签</option><option value="pick">正选</option>
      <option value="alt">替补</option><option value="drop">剔除</option><option value="todo">未定</option>
    </select>
    <input type="search" id="f-q" placeholder="搜 id / 反应名 / SMILES" size="22">
    <button onclick="exportJSON()">导出 JSON</button>
    <button onclick="exportNames()">导出名单</button>
    <button onclick="document.getElementById('importwrap').classList.toggle('hidden')">导入 JSON</button>
    <button onclick="resetDefaults()">重置为旧建议名单</button>
    <button onclick="clearAll()">全部清空</button>
  </div>
  <div id="importwrap" class="hidden" style="margin-top:8px">
    <textarea id="importbox" placeholder='粘贴之前导出的 JSON（{"tags": {"A1": "pick", ...}}）'></textarea>
    <button onclick="importJSON()">导入</button>
  </div>
</header>
<main>
<table>
  <thead><tr>
    <th>#</th><th>打标</th><th>带/族</th><th>反应</th><th>SMILES, q/mult</th>
    <th class="mech">机理概要</th><th class="barrier">能垒锚点</th><th>舒适区</th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table>
</main>
<script>
const ENTRIES = __DATA__;
const LS_KEY = "normal-tagging-v1";
let tags = {};
try { tags = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (e) { tags = {}; }
if (!Object.keys(tags).length) {
  for (const e of ENTRIES) if (e.def) tags[e.id] = e.def;
}

function save() { localStorage.setItem(LS_KEY, JSON.stringify(tags)); }
function esc(s) { return s; }

function render() {
  const fb = document.getElementById("f-band").value;
  const ff = document.getElementById("f-fam").value;
  const ft = document.getElementById("f-tag").value;
  const q = document.getElementById("f-q").value.trim().toLowerCase();
  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  const counts = { pick: 0, alt: 0, drop: 0, todo: 0 };
  for (const e of ENTRIES) {
    const st = tags[e.id] || "todo";
    counts[st] = (counts[st] || 0) + 1;
    if (fb && e.band !== fb) continue;
    if (ff && e.family !== ff) continue;
    if (ft && st !== ft) continue;
    if (q && !(e.id.toLowerCase().includes(q) || e.name.toLowerCase().includes(q) || e.smiles.toLowerCase().includes(q))) continue;
    const tr = document.createElement("tr");
    tr.className = "st-" + st;
    const cells = [
      `<td class="id">${e.id}</td>`,
      `<td class="tag-btns">
         <button class="b-pick ${st === "pick" ? "on" : ""}" onclick="setTag('${e.id}','pick')">正选</button>
         <button class="b-alt ${st === "alt" ? "on" : ""}" onclick="setTag('${e.id}','alt')">替补</button>
         <button class="b-drop ${st === "drop" ? "on" : ""}" onclick="setTag('${e.id}','drop')">剔除</button>
       </td>`,
      `<td><span class="band">${e.band}</span><br><span class="band">${e.family} 族</span></td>`,
      `<td>${e.name}</td>`,
      `<td><code>${e.smiles}</code><br>${e.qm}</td>`,
      `<td class="mech">${e.mech}</td>`,
      `<td class="barrier">${e.barrier} <span class="vtag v-${e.verify}">${e.verify}</span></td>`,
      `<td>${e.comfort}</td>`,
    ];
    tr.innerHTML = cells.join("");
    tb.appendChild(tr);
  }
  const cp = document.getElementById("c-pick");
  cp.innerHTML = `正选 <b>${counts.pick || 0}</b>/30`;
  cp.className = "counter" + ((counts.pick || 0) > 30 ? " over" : "");
  document.getElementById("c-alt").innerHTML = `替补 <b>${counts.alt || 0}</b>/10`;
  document.getElementById("c-drop").innerHTML = `剔除 <b>${counts.drop || 0}</b>`;
  document.getElementById("c-todo").innerHTML = `未定 <b>${counts.todo || 0}</b>`;
}

function setTag(id, st) {
  tags[id] = (tags[id] === st) ? "todo" : st;
  if (tags[id] === "todo") delete tags[id];
  save(); render();
}

function exportJSON() {
  const blob = new Blob([JSON.stringify({ tags }, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "normal_tags.json";
  a.click();
}

function exportNames() {
  const pick = ENTRIES.filter(e => tags[e.id] === "pick").map(e => e.id);
  const alt = ENTRIES.filter(e => tags[e.id] === "alt").map(e => e.id);
  const drop = ENTRIES.filter(e => tags[e.id] === "drop").map(e => e.id);
  const txt = `正选 ${pick.length}：${pick.join(", ")}\n\n替补 ${alt.length}：${alt.join(", ")}\n\n剔除 ${drop.length}：${drop.join(", ")}\n`;
  const blob = new Blob([txt], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "normal_selection.txt";
  a.click();
}

function importJSON() {
  try {
    const obj = JSON.parse(document.getElementById("importbox").value);
    tags = obj.tags || obj;
    save(); render();
    document.getElementById("importwrap").classList.add("hidden");
  } catch (e) { alert("JSON 解析失败：" + e); }
}

function resetDefaults() {
  if (!confirm("把所有条目的打标重置为旧建议名单（正选 30 / 替补 10，新条目未定）？")) return;
  tags = {};
  for (const e of ENTRIES) if (e.def) tags[e.id] = e.def;
  save(); render();
}

function clearAll() {
  if (!confirm("清空全部打标？")) return;
  tags = {}; save(); render();
}

for (const id of ["f-band", "f-fam", "f-tag", "f-q"]) document.getElementById(id).addEventListener("input", render);
const bands = [...new Set(ENTRIES.map(e => e.band))];
const fams = [...new Set(ENTRIES.map(e => e.family))];
for (const b of bands) document.getElementById("f-band").insertAdjacentHTML("beforeend", `<option>${b}</option>`);
for (const f of fams) document.getElementById("f-fam").insertAdjacentHTML("beforeend", `<option>${f} 族</option>`);
render();
</script>
</body>
</html>
"""


def parse_entries() -> list[dict]:
    band_of = {tid: band for band, ids in BANDS.items() for tid in ids}
    entries = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        tid = m.group(1)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            raise SystemExit(f"{tid}: 行解析失败（列数 {len(cells)}）")
        sm = SMILES_RE.search(cells[2])
        if not sm:
            raise SystemExit(f"{tid}: SMILES 格解析失败")
        vm = VERIFY_RE.search(cells[5])
        default = "pick" if tid in SUGGESTED_PICK else "alt" if tid in SUGGESTED_ALT else None
        entries.append({
            "id": tid,
            "band": band_of.get(tid, "?"),
            "family": tid[0],
            "name": cells[1],
            "smiles": sm.group(1),
            "qm": f"{sm.group(2)}/{sm.group(3)}",
            "mech": cells[4],
            "barrier": cells[5],
            "verify": vm.group(1) if vm else "未核实",
            "comfort": cells[6],
            "def": default,
        })
    return entries


def main() -> None:
    entries = parse_entries()
    missing = [e["id"] for e in entries if e["band"] == "?"]
    if missing:
        raise SystemExit(f"以下条目未登记三带映射（在 BANDS 里补上）：{missing}")
    data = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA__", data).replace("__N__", str(len(entries)))
    OUT.write_text(html, encoding="utf-8")
    print(f"OK: {len(entries)} 条 → {OUT}")


if __name__ == "__main__":
    main()
