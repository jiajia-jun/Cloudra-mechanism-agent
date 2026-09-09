"""从 ideapool/reaction_candidates/impossible.md 生成 Impossible 档评审打标台（自包含 HTML）。

用法：.venv/bin/python scripts/gen_impossible_tagging.py
产物：ideapool/reaction_candidates/impossible_tagging.html（浏览器直接打开；
打标状态存 localStorage，可导出/导入 JSON，可导出正选/替补名单文本）。

池子条目变更后重跑本脚本即可重建打标台；localStorage 里的打标按条目 id 对齐，
增删条目不会串位。打标台只是一层标注 UI，不回写 impossible.md——名单定稿后人工更新。

与 hard 打标台的差异：impossible.md 是 `### ID. 标题` + 7 个编号字段的小节格式
（非表格），解析器按小节切；每条证据链很长，UI 提供"详"按钮就地展开全文；
无打标带映射，改为族过滤 + 边缘标注过滤。2026-09-01 已定稿（正选 20 / 剔除 6），
打标台默认值为定稿名单（权威以 impossible.md 文末"定稿圈定"段为准）。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ideapool" / "reaction_candidates" / "impossible.md"
OUT = ROOT / "ideapool" / "reaction_candidates" / "impossible_tagging.html"

FAMILY_RE = re.compile(r"^##\s+([A-J])\.\s+([^（(]+)")
ENTRY_RE = re.compile(r"^###\s+([A-J]\d+)\.\s+(.+?)\s*$")
FIELD_RE = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*[:：]\s*(.*)$")
EDGE_RE = re.compile(r"【(.+?)】")
SMILES_RE = re.compile(r"`([^`]+)`")
FIELD_ORDER = ["体系", "结构", "多参考性质", "诊断证据", "兄弟题", "权威性依据", "拒答判据"]

# 2026-09-01 打标定稿名单（impossible.md"定稿圈定"段为权威；此处只作打标台初始默认值）。
SUGGESTED_PICK = "A1 A5 A7 A8 A9 C3 D2 E2 F3 G8".split()  # v3 2026-09-09 (20 -> 10 pool ids)
SUGGESTED_DROP = "A2 A3 A4 A6 B1 H2".split()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Impossible 档打标台（__N__ 条候选）</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif; margin: 0; background: #0f1115; color: #d7dae0; }
  header { position: sticky; top: 0; z-index: 10; background: #161a22; border-bottom: 1px solid #2a2f3a; padding: 10px 16px; }
  header h1 { font-size: 15px; margin: 0 0 8px; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 13px; margin-top: 6px; }
  .counter { padding: 2px 10px; border-radius: 10px; background: #222836; font-variant-numeric: tabular-nums; }
  .counter b { color: #7ec8ff; }
  .counter.over b { color: #ff7e7e; }
  select, input[type=search] { background: #1d2230; color: #d7dae0; border: 1px solid #333a4a; border-radius: 6px; padding: 4px 8px; font-size: 13px; }
  button { background: #1d2230; color: #d7dae0; border: 1px solid #333a4a; border-radius: 6px; padding: 4px 10px; font-size: 12.5px; cursor: pointer; }
  button:hover { border-color: #5a6580; }
  main { padding: 12px 16px 60px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { border-bottom: 1px solid #242a36; padding: 7px 8px; text-align: left; vertical-align: top; }
  th { position: sticky; top: 118px; background: #161a22; font-size: 12px; color: #8b93a5; }
  td.id { font-weight: 700; white-space: nowrap; }
  code { font-size: 11.5px; color: #9fd3a8; word-break: break-all; }
  .fam { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: #222836; white-space: nowrap; }
  .edge { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: #3a2a4a; color: #d3b3f0; white-space: nowrap; }
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
  .v-约 { background: #4a3a1d; color: #f0d59a; }
  .v-未核实 { background: #4a1d22; color: #f0a3ab; }
  .mr, .sib { max-width: 380px; }
  .name { max-width: 300px; }
  .sm { max-width: 260px; }
  .hidden { display: none; }
  tr.detail td { background: #141824; }
  tr.detail pre { white-space: pre-wrap; word-break: break-word; font-size: 12.5px; line-height: 1.55; margin: 4px 0; color: #c9cfdb; max-width: 1200px; }
  textarea#importbox { width: 100%; height: 90px; background: #1d2230; color: #d7dae0; border: 1px solid #333a4a; }
</style>
</head>
<body>
<header>
  <h1>Impossible 档打标台（强多参考/近简并双自由基）· __N__ 条候选 · 已定稿：正选 20 / 剔除 6（打标存 localStorage，不回写 impossible.md）</h1>
  <div class="bar">
    <span class="counter" id="c-pick">正选 <b>0</b>/10</span>
    <span class="counter" id="c-alt">替补 <b>0</b></span>
    <span class="counter" id="c-drop">剔除 <b>0</b></span>
    <span class="counter" id="c-todo">未定 <b>0</b></span>
    <span class="counter" id="c-fams" title="各族正选数">各族正选：—</span>
  </div>
  <div class="bar">
    <select id="f-fam"><option value="">全部族</option></select>
    <select id="f-edge">
      <option value="">全部条目</option><option value="edge">仅边缘标注</option><option value="nonedge">仅无标注</option>
    </select>
    <select id="f-tag">
      <option value="">全部标签</option><option value="pick">正选</option>
      <option value="alt">替补</option><option value="drop">剔除</option><option value="todo">未定</option>
    </select>
    <input type="search" id="f-q" placeholder="搜 id / 名称 / SMILES / 性质" size="24">
    <button onclick="exportJSON()">导出 JSON</button>
    <button onclick="exportNames()">导出名单</button>
    <button onclick="document.getElementById('importwrap').classList.toggle('hidden')">导入 JSON</button>
    <button onclick="resetDefaults()">重置为定稿名单</button>
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
    <th>#</th><th>打标</th><th>族</th><th>体系</th><th>SMILES</th>
    <th class="mr">多参考性质</th><th class="sib">兄弟题</th><th>标记</th><th></th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table>
</main>
<script>
const ENTRIES = __DATA__;
const LS_KEY = "impossible-tagging-v1";
let tags = {};
try { tags = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (e) { tags = {}; }
if (!Object.keys(tags).length) {
  for (const e of ENTRIES) if (e.def) tags[e.id] = e.def;
}

function save() { localStorage.setItem(LS_KEY, JSON.stringify(tags)); }
function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function cut(s, n) { s = s || ""; return s.length > n ? esc(s.slice(0, n)) + "…" : esc(s); }

function render() {
  const ff = document.getElementById("f-fam").value;
  const fe = document.getElementById("f-edge").value;
  const ft = document.getElementById("f-tag").value;
  const q = document.getElementById("f-q").value.trim().toLowerCase();
  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  const counts = { pick: 0, alt: 0, drop: 0, todo: 0 };
  const famPick = {};
  for (const e of ENTRIES) {
    const st = tags[e.id] || "todo";
    counts[st] = (counts[st] || 0) + 1;
    if (st === "pick") famPick[e.family] = (famPick[e.family] || 0) + 1;
    if (ff && e.family !== ff) continue;
    if (fe === "edge" && !e.edge) continue;
    if (fe === "nonedge" && e.edge) continue;
    if (ft && st !== ft) continue;
    if (q && !(e.id.toLowerCase().includes(q) || e.name.toLowerCase().includes(q)
        || e.smiles.toLowerCase().includes(q) || e.mr.toLowerCase().includes(q))) continue;
    const tr = document.createElement("tr");
    tr.className = "st-" + st;
    tr.innerHTML = [
      `<td class="id">${e.id}${e.edge ? `<br><span class="edge">${esc(e.edge)}</span>` : ""}</td>`,
      `<td class="tag-btns">
         <button class="b-pick ${st === "pick" ? "on" : ""}" onclick="setTag('${e.id}','pick')">正选</button>
         <button class="b-alt ${st === "alt" ? "on" : ""}" onclick="setTag('${e.id}','alt')">替补</button>
         <button class="b-drop ${st === "drop" ? "on" : ""}" onclick="setTag('${e.id}','drop')">剔除</button>
       </td>`,
      `<td><span class="fam">${e.family} 族</span><br><span class="fam">${esc(e.familyName)}</span></td>`,
      `<td class="name">${esc(e.name)}</td>`,
      `<td class="sm"><code>${cut(e.smiles, 90)}</code></td>`,
      `<td class="mr">${cut(e.mr, 120)}</td>`,
      `<td class="sib">${cut(e.sibling, 90)}</td>`,
      `<td><span class="vtag v-${e.verify}">${e.verify}</span></td>`,
      `<td><button onclick="toggleDetail('${e.id}')">详</button></td>`,
    ].join("");
    tb.appendChild(tr);
    const dr = document.createElement("tr");
    dr.className = "detail hidden";
    dr.id = "detail-" + e.id;
    dr.innerHTML = `<td></td><td colspan="8"><pre>${esc(e.raw)}</pre></td>`;
    tb.appendChild(dr);
  }
  const cp = document.getElementById("c-pick");
  cp.innerHTML = `正选 <b>${counts.pick || 0}</b>/10`;
  cp.className = "counter" + ((counts.pick || 0) > 10 ? " over" : "");
  document.getElementById("c-alt").innerHTML = `替补 <b>${counts.alt || 0}</b>`;
  document.getElementById("c-drop").innerHTML = `剔除 <b>${counts.drop || 0}</b>`;
  document.getElementById("c-todo").innerHTML = `未定 <b>${counts.todo || 0}</b>`;
  const famStr = Object.keys(famPick).sort().map(k => k + ":" + famPick[k]).join(" ");
  document.getElementById("c-fams").textContent = "各族正选：" + (famStr || "—");
}

function toggleDetail(id) {
  document.getElementById("detail-" + id).classList.toggle("hidden");
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
  a.download = "impossible_tags.json";
  a.click();
}

function exportNames() {
  const pick = ENTRIES.filter(e => tags[e.id] === "pick").map(e => e.id);
  const alt = ENTRIES.filter(e => tags[e.id] === "alt").map(e => e.id);
  const drop = ENTRIES.filter(e => tags[e.id] === "drop").map(e => e.id);
  const txt = `正选 ${pick.length}：${pick.join(", ")}\\n\\n替补 ${alt.length}：${alt.join(", ")}\\n\\n剔除 ${drop.length}：${drop.join(", ")}\\n`;
  const blob = new Blob([txt], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "impossible_selection.txt";
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
  if (!confirm("把所有条目的打标重置为定稿名单（正选 20 / 剔除 6，其余未定）？")) return;
  tags = {};
  for (const e of ENTRIES) if (e.def) tags[e.id] = e.def;
  save(); render();
}

function clearAll() {
  if (!confirm("清空全部打标？")) return;
  tags = {}; save(); render();
}

for (const id of ["f-fam", "f-edge", "f-tag", "f-q"]) document.getElementById(id).addEventListener("input", render);
const fams = [...new Set(ENTRIES.map(e => e.family))];
for (const f of fams) document.getElementById("f-fam").insertAdjacentHTML("beforeend", `<option value="${f}">${f} 族</option>`);
render();
</script>
</body>
</html>
"""


def parse_entries() -> list[dict]:
    family_names: dict[str, str] = {}
    blocks: list[tuple[str, str, list[str]]] = []  # (id, title, field lines)
    cur: tuple[str, str, list[str]] | None = None
    for line in SRC.read_text(encoding="utf-8").splitlines():
        fm = FAMILY_RE.match(line)
        if fm:
            family_names[fm.group(1)] = fm.group(2).strip()
            cur = None
            continue
        if line.startswith("## "):  # 检索说明 / 附：… 等二级段，结束当前条目
            cur = None
            continue
        em = ENTRY_RE.match(line)
        if em:
            cur = (em.group(1), em.group(2), [])
            blocks.append(cur)
            continue
        if cur is not None and FIELD_RE.match(line):
            cur[2].append(line.strip())

    entries = []
    for tid, title, lines in blocks:
        fields = {}
        for ln in lines:
            m = FIELD_RE.match(ln)
            fields[m.group(1)] = m.group(2).strip()
        edge_m = EDGE_RE.search(title)
        edge = edge_m.group(1) if edge_m else ""
        name = EDGE_RE.sub("", title).strip()
        structure = fields.get("结构", "")
        smiles = " / ".join(SMILES_RE.findall(structure)) or "—"
        joined = " ".join(fields.values())
        verify = "未核实" if "[未核实" in joined else ("约" if "[约" in joined else "已核实")
        default = "pick" if tid in SUGGESTED_PICK else ("drop" if tid in SUGGESTED_DROP else None)
        raw = f"### {tid}. {title}\n" + "\n".join(
            f"{i}. **{k}**：{fields[k]}" for i, k in enumerate(FIELD_ORDER, 1) if k in fields
        )
        entries.append({
            "id": tid,
            "family": tid[0],
            "familyName": family_names.get(tid[0], "?"),
            "name": name,
            "edge": edge,
            "smiles": smiles,
            "mr": fields.get("多参考性质", ""),
            "sibling": fields.get("兄弟题", ""),
            "verify": verify,
            "def": default,
            "raw": raw,
        })
    return entries


def main() -> None:
    entries = parse_entries()
    if len(entries) != 70:
        raise SystemExit(f"条目数 {len(entries)} ≠ 70，解析有误，请检查 impossible.md 格式")
    data = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA__", data).replace("__N__", str(len(entries)))
    OUT.write_text(html, encoding="utf-8")
    fams: dict[str, int] = {}
    for e in entries:
        fams[e["family"]] = fams.get(e["family"], 0) + 1
    stats = " ".join(f"{k}:{v}" for k, v in sorted(fams.items()))
    print(f"OK: {len(entries)} 条（{stats}）→ {OUT}")


if __name__ == "__main__":
    main()
