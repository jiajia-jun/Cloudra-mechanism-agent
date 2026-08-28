#!/usr/bin/env python3
"""Generate easy_review.html — interactive screening page for the Easy-tier
reaction candidate pool (29 candidates, focused on 7 reaction families).

Data flow: rows are parsed verbatim from easy.md markdown tables. The page is a
single self-contained HTML file: vanilla JS, localStorage persistence, JSON export.
Optionally re-validates every SMILES with RDKit (same check as pool construction).
"""
import datetime
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "easy.md"

GROUP_NAMES = {
    "D": "Diels-Alder 环加成",
    "P": "σ 迁移重排（[3,3]/[1,5]-H）",
    "C": "SN2 亲核取代",
    "E": "E2 消除",
    "F": "羰基亲核加成 / 还原",
    "T": "质子转移 / 互变异构",
}

# 2026-08-28 重构后聚焦七类（DA/σ迁移/SN2/E2/羰基加成/质子转移），
# 不再维护 shortlist/alternates 二级筛选，全部条目均为正式候选。
SHORTLIST: list = []
ALTERNATES: list = []

ROW_RE = re.compile(r"^\|\s*([DPECTF]\d+)\s*\|(.*)\|\s*$")


def split_cells(body: str):
    """Split markdown row body on unescaped pipes."""
    cells, cur, esc = [], "", False
    for ch in body:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
            cur += ch
        elif ch == "|":
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def verify_status(anchor: str) -> str:
    if "已核实" in anchor:
        return "verified"
    if "部分核实" in anchor:
        return "partial"
    return "unverified"


def parse():
    entries = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        cid, body = m.group(1), m.group(2)
        cells = split_cells(body)
        # comfort cell always contains ✅; stray pipes inside the anchor cell
        # (e.g. |ΔHrxn|) inflate the count, so merge overflow back into anchor.
        ci = next((i for i, c in enumerate(cells) if "✅" in c), -1)
        if ci < 5 or ci != len(cells) - 2:
            continue
        name, smiles, conds, mech = cells[0], cells[1], cells[2], cells[3]
        anchor = " | ".join(cells[4:ci])
        comfort, classic = cells[ci], cells[ci + 1]
        # strip backticks and the trailing "，q/mult" charge/multiplicity suffix
        smi = re.sub(r"[`*]", "", smiles).strip()
        smi = re.split(r"[，,]\s*[−\-]?\d+\s*/\s*\d+\s*$", smi)[0].strip()
        # drop parenthetical remarks like "（须 Z 构型）"
        smi = re.sub(r"（[^）]*）", "", smi).strip()
        entries.append({
            "id": cid,
            "group": cid[0],
            "group_name": GROUP_NAMES[cid[0]],
            "name": name,
            "smiles": smi,
            "conds": conds,
            "mech": mech,
            "anchor": anchor,
            "comfort": comfort,
            "classic": classic,
            "status": verify_status(anchor),
            "role": ("shortlist" if cid in SHORTLIST
                     else "alternate" if cid in ALTERNATES else "pool"),
            "smiles_ok": None,  # filled by optional RDKit pass below
        })
    order = {cid: i for i, cid in enumerate(SHORTLIST)}
    entries.sort(key=lambda e: (e["group"], order.get(e["id"], 99), e["id"]))
    return entries


def rdkit_check(entries):
    try:
        from rdkit import Chem
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        print("note: RDKit not available, skipping SMILES re-validation")
        return
    bad = 0
    for e in entries:
        ok = True
        for part in e["smiles"].split(">>"):
            for frag in part.split("."):
                frag = frag.strip()
                if frag and Chem.MolFromSmiles(frag) is None:
                    ok = False
        e["smiles_ok"] = ok
        if not ok:
            bad += 1
            print(f"  SMILES FAIL: {e['id']} {e['smiles']}")
    print(f"RDKit re-validation: {len(entries) - bad}/{len(entries)} ok")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Easy 档候选反应评审台（47 → 30）</title>
<style>
:root{
  --bg:#f6f7f9; --card:#fff; --ink:#1c2330; --muted:#6b7280; --line:#e5e7eb;
  --accept:#16a34a; --reject:#dc2626; --pend:#d97706;
  --verified:#16a34a; --partial:#d97706; --unverified:#dc2626;
  --shortlist:#2563eb; --alternate:#7c3aed;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
  "Hiragino Sans GB","Microsoft YaHei",sans-serif}
.topbar{position:sticky;top:0;z-index:10;background:#ffffffee;
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 20px 8px}
.topbar h1{font-size:17px;margin:0 0 2px}
.topbar .sub{font-size:12px;color:var(--muted)}
.counts{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-top:6px;font-weight:600}
.counts .c{display:inline-flex;align-items:center;gap:4px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.goal{font-weight:700}
.goal.ok{color:var(--accept)} .goal.over{color:var(--reject)} .goal.under{color:var(--pend)}
.bar{height:4px;background:var(--line);border-radius:2px;margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;background:#2563eb;width:0%;transition:width .25s}
.controls{max-width:1080px;margin:12px auto;padding:0 16px;display:flex;
  gap:8px;flex-wrap:wrap;align-items:center;position:sticky;top:118px;z-index:9}
.chip{border:1px solid var(--line);background:var(--card);border-radius:999px;
  padding:4px 12px;font-size:13px;cursor:pointer;user-select:none}
.chip.on{background:#1c2330;color:#fff;border-color:#1c2330}
.chip .n{opacity:.65;font-weight:400;margin-left:2px}
.search{flex:1;min-width:160px;border:1px solid var(--line);border-radius:999px;
  padding:5px 14px;font-size:13px;background:var(--card)}
.btn{border:1px solid var(--line);background:var(--card);border-radius:8px;
  padding:5px 12px;font-size:13px;cursor:pointer}
.btn:hover{background:#f0f2f5}
.btn.primary{background:#2563eb;color:#fff;border-color:#2563eb}
main{max-width:1080px;margin:0 auto;padding:4px 16px 80px}
.sechead{margin:26px 0 10px;font-size:15px;font-weight:700;display:flex;
  align-items:center;gap:8px;flex-wrap:wrap}
.sechead .t-dot{width:11px;height:11px;border-radius:3px;background:#2563eb}
.sechead .cnt{font-size:12px;color:var(--muted);font-weight:400}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:13px 16px 11px;margin-bottom:11px;border-left:4px solid var(--line)}
.card.d-accept{background:#f0fdf4;border-color:#bbf7d0}
.card.d-reject{opacity:.5;background:#fafafa}
.card.d-pending{background:#fffbeb;border-color:#fde68a}
.cardhead{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px}
.tid{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;
  background:#eef1f5;border-radius:5px;padding:1px 7px;font-weight:700}
.badge{font-size:11px;border-radius:5px;padding:1px 7px;font-weight:600}
.badge.shortlist{background:#dbeafe;color:#1e40af}
.badge.alternate{background:#ede9fe;color:#5b21b6}
.badge.pool{background:#f3f4f6;color:#4b5563}
.badge.verified{background:#dcfce7;color:#166534}
.badge.partial{background:#fef3c7;color:#92400e}
.badge.unverified{background:#fee2e2;color:#991b1b}
.badge.smiles-bad{background:#7f1d1d;color:#fff}
.card h3{font-size:15px;margin:2px 0 3px;line-height:1.45}
.smi{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;
  background:#f8fafc;border:1px solid var(--line);border-radius:6px;
  padding:3px 8px;display:inline-block;margin:2px 0 4px;word-break:break-all}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:2px 18px;font-size:13px;margin-top:4px}
.grid .k{color:var(--muted);font-size:12px}
.grid .full{grid-column:1/-1}
.anchor-box{font-size:12.5px;border-radius:8px;padding:6px 10px;margin-top:7px}
.anchor-box.verified{background:#f0fdf4;color:#14532d}
.anchor-box.partial{background:#fffbeb;color:#78350f}
.anchor-box.unverified{background:#fef2f2;color:#7f1d1d}
.decide{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
.d-btn{border:1.5px solid var(--line);background:#fff;border-radius:8px;
  padding:5px 13px;font-size:13px;cursor:pointer;font-weight:600}
.d-btn.accept:hover,.d-btn.accept.on{background:var(--accept);color:#fff;border-color:var(--accept)}
.d-btn.reject:hover,.d-btn.reject.on{background:var(--reject);color:#fff;border-color:var(--reject)}
.d-btn.pending:hover,.d-btn.pending.on{background:var(--pend);color:#fff;border-color:var(--pend)}
.note{flex:1;min-width:140px;border:1px solid var(--line);border-radius:8px;
  padding:5px 10px;font-size:12.5px}
.saved{font-size:11px;color:var(--muted)}
kbd{background:#eef1f5;border:1px solid var(--line);border-radius:4px;
  padding:0 5px;font-size:11.5px;font-family:ui-monospace,monospace}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);
  margin:14px 0 4px;padding:10px 14px;background:#fff;border:1px solid var(--line);border-radius:10px}
.legend b{color:var(--ink)}
.lg{display:inline-block;width:14px;height:9px;border-radius:2px;vertical-align:baseline}
.toast{position:fixed;left:50%;bottom:30px;transform:translateX(-50%);
  background:#1c2330;color:#fff;border-radius:8px;padding:8px 18px;
  font-size:13px;opacity:0;transition:opacity .25s;pointer-events:none;z-index:99}
.toast.show{opacity:.95}
footer{max-width:1080px;margin:30px auto;padding:0 16px 40px;
  font-size:12px;color:var(--muted)}
@media (max-width:720px){.grid{grid-template-columns:1fr}}
@media print{.controls,.decide,.topbar{display:none}}
</style>
</head>
<body>
<div class="topbar">
  <h1>Easy 档候选反应评审台 — 47 选 30</h1>
  <div class="sub">数据源 ideapool/reaction_candidates/easy.md（2026-08-25 生成，47 条）｜本页生成于 __GEN_DATE__｜打标自动存 localStorage，「⬇ 导出JSON」存档后把文件发回即可落库</div>
  <div class="counts" id="counts"></div>
  <div class="bar"><i id="pbar"></i></div>
</div>
<div class="controls">
  <span id="groupChips"></span>
  <span style="width:1px;height:22px;background:var(--line)"></span>
  <span id="statusChips"></span>
  <input class="search" id="q" type="search" placeholder="搜索编号 / 反应名 / SMILES / 关键词…">
  <button class="btn primary" id="exportJson">⬇ 导出JSON</button>
  <button class="btn" id="copyList">📋 复制入选清单</button>
  <label class="btn" style="position:relative;overflow:hidden">导入
    <input type="file" id="importJson" accept=".json" style="position:absolute;inset:0;opacity:0;cursor:pointer">
  </label>
</div>
<main>
<div class="legend">
  <span><b>遴选标准</b>：机理共识最硬 + 锚点已核实 + 类型不重复 + 能垒梯度拉开 + MACE-OMol25 舒适区命中</span>
  <span><span class="lg" style="background:#a7f3d0"></span> 低能垒 &lt;15</span>
  <span><span class="lg" style="background:#fde68a"></span> 中 15–35</span>
  <span><span class="lg" style="background:#fecaca"></span> 高 &gt;35 kcal/mol</span>
  <span>键盘：<kbd>A</kbd> 收录 <kbd>P</kbd> 待定 <kbd>X</kbd> 排除（作用于当前鼠标悬停卡片）</span>
</div>
<div id="list"></div>
</main>
<footer>
  <b>评审口径</b>（来自 easy.md）：评分绑定 agent 实际计算证据（TS+IRC+频率），不回避知名反应，只要求机理共识无争议；
  阴离子体系 gold 口径（中央能垒 vs 相对渐近线）入选后在题目卡写死；
  标记 [未核实] 的条目若入选，需先做一次针对性文献复查（±2 kcal/mol 内即可，出处必须真实）。<br>
  目标：收录 = 30。top-15 蓝标为原清单优先池（建议全收），紫标为备选替换位。收录数超过 30 时计数器变红提示回退。
</footer>
<div class="toast" id="toast"></div>

<script>
const DATA = __PAYLOAD__;
const KEY = "cloudra_easy_review_v1";
const GROUPS = ["A","B","C","D","E","F","G"];
const GROUP_LABEL = {A:"A 周环",B:"B [3+2]",C:"C SN2",D:"D E2",E:"E 互变/PT",F:"F 羰基加成",G:"G 其他加成"};
const STATUS = ["all","untagged","accept","pending","reject"];
const STATUS_LABEL = {all:"全部",untagged:"未标",accept:"✅ 收录",pending:"⏸ 待定",reject:"❌ 排除"};
const ROLE_LABEL = {shortlist:"⭐ top-15 优先池",alternate:"🔁 备选替换位",pool:"池内"};
const VER_LABEL = {verified:"已核实",partial:"部分核实",unverified:"未核实"};

function loadState(){ try{return JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){return {}} }
let state = loadState();
let filt = {group:"all", status:"all", q:""};

const esc = s => String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;")
  .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const $ = id => document.getElementById(id);

function getRec(id){ return state[id] || {}; }
function setRec(id, rec){ if(rec && (rec.d || rec.n)) state[id]=rec; else delete state[id];
  localStorage.setItem(KEY, JSON.stringify(state)); }
function counts(){
  let c={accept:0,pending:0,reject:0,untagged:0};
  DATA.forEach(e=>{ const d=getRec(e.id).d; if(d&&c[d]!=null)c[d]++; else c.untagged++; });
  return c;
}
function toast(msg){ const t=$("toast"); t.textContent=msg; t.classList.add("show");
  clearTimeout(t._tm); t._tm=setTimeout(()=>t.classList.remove("show"),2200); }

// crude barrier estimate for the color legend: first number found in anchor text
function barrierOf(e){
  const nums = (e.anchor.replace(/[−–—]/g,"-").match(/\d+(?:\.\d+)?/g)||[]).map(Number)
    .filter(n=>n>=1&&n<=120);
  if(!nums.length) return null;
  if(/≈\s*([\d.]+)\s*-\s*([\d.]+)/.test(e.anchor)){
    const m=e.anchor.match(/≈\s*([\d.]+)\s*-\s*([\d.]+)/);
    return (parseFloat(m[1])+parseFloat(m[2]))/2;
  }
  return nums[0];
}
function barrierBg(e){
  const b=barrierOf(e);
  if(b==null) return "transparent";
  if(b<15) return "#a7f3d0";
  if(b<=35) return "#fde68a";
  return "#fecaca";
}

function cardHtml(e){
  const r=getRec(e.id), d=r.d||"", note=r.n||"";
  const smiBad = e.smiles_ok===false;
  return `<article class="card ${d?("d-"+d):""}" data-id="${e.id}">
    <div class="cardhead">
      <span class="tid">${e.id}</span>
      <span class="badge ${e.role}">${ROLE_LABEL[e.role]}</span>
      <span class="badge ${e.status}">${VER_LABEL[e.status]}</span>
      ${smiBad?'<span class="badge smiles-bad">SMILES 校验失败</span>':''}
      <span style="flex:1"></span>
      <span class="saved">${r.t?("已保存 "+r.t):""}</span>
    </div>
    <h3>${esc(e.name)}</h3>
    <div><span class="smi">${esc(e.smiles)}</span></div>
    <div class="grid">
      <div class="full"><span class="k">条件</span> ${esc(e.conds)}</div>
      <div class="full"><span class="k">机理</span> ${esc(e.mech)}</div>
      <div><span class="k">舒适区</span> ${esc(e.comfort)}</div>
      <div><span class="k">经典性</span> ${esc(e.classic)}</div>
    </div>
    <div class="anchor-box ${e.status}" style="border-left:6px solid ${barrierBg(e)}">
      ⚓ ${esc(e.anchor)}
    </div>
    <div class="decide">
      <button class="d-btn accept ${d==="accept"?"on":""}">✅ 收录</button>
      <button class="d-btn pending ${d==="pending"?"on":""}">⏸ 待定</button>
      <button class="d-btn reject ${d==="reject"?"on":""}">❌ 排除</button>
      <input class="note" placeholder="备注（可选，自动保存）" value="${esc(note)}">
    </div>
  </article>`;
}

function render(){
  const c=counts(), total=DATA.length, tagged=total-c.untagged;
  const cls = c.accept===30?"ok":(c.accept>30?"over":"under");
  $("counts").innerHTML =
    `<span class="c goal ${cls}">收录 ${c.accept} / 30</span>`+
    `<span class="c"><span class="dot" style="background:var(--pend)"></span>待定 ${c.pending}</span>`+
    `<span class="c"><span class="dot" style="background:var(--reject)"></span>排除 ${c.reject}</span>`+
    `<span class="c"><span class="dot" style="background:#cbd5e1"></span>未标 ${c.untagged}</span>`+
    `<span class="c" style="color:var(--muted);font-weight:400">已核 ${DATA.filter(e=>e.status==="verified").length}｜部分 ${DATA.filter(e=>e.status==="partial").length}｜未核 ${DATA.filter(e=>e.status==="unverified").length}</span>`;
  $("pbar").style.width=(tagged/total*100).toFixed(1)+"%";

  $("groupChips").innerHTML=[["all","全部"]].concat(GROUPS.map(g=>[g,GROUP_LABEL[g]]))
    .map(([v,l])=>{ const n=v==="all"?total:DATA.filter(e=>e.group===v).length;
      return `<button class="chip ${filt.group===v?"on":""}" data-k="group" data-v="${v}">${l}<span class="n">${n}</span></button>`;}).join("");
  $("statusChips").innerHTML=STATUS.map(v=>{
    const n=v==="all"?total:c[v];
    return `<button class="chip ${filt.status===v?"on":""}" data-k="status" data-v="${v}">${STATUS_LABEL[v]}<span class="n">${n}</span></button>`;}).join("");

  const q=filt.q.trim().toLowerCase();
  let html="", shown=0;
  GROUPS.filter(g=>filt.group==="all"||filt.group===g).forEach(g=>{
    const es=DATA.filter(e=>e.group===g &&
      (filt.status==="all" || (filt.status==="untagged"?!getRec(e.id).d:getRec(e.id).d===filt.status)) &&
      (!q || (e.id+" "+e.name+" "+e.smiles+" "+e.mech+" "+e.anchor+" "+e.classic).toLowerCase().includes(q)));
    if(!es.length) return;
    shown+=es.length;
    const acc=es.filter(e=>getRec(e.id).d==="accept").length;
    html+=`<div class="sechead"><span class="t-dot"></span>${GROUP_LABEL[g]}（${es[0].group_name}）
      <span class="cnt">${es.length} 条｜已收录 ${acc}</span></div>`;
    html+=es.map(cardHtml).join("");
  });
  $("list").innerHTML = shown ? html :
    `<p style="color:var(--muted);text-align:center;margin-top:60px">没有符合当前筛选条件的候选。</p>`;
}

let hoverId = null;
document.addEventListener("mouseover", ev=>{
  const card=ev.target.closest(".card"); hoverId = card ? card.dataset.id : null;
});
document.addEventListener("keydown", ev=>{
  if(!hoverId || ev.target.tagName==="INPUT") return;
  const map={a:"accept",p:"pending",x:"reject"};
  const d=map[ev.key.toLowerCase()]; if(!d) return;
  const rec=getRec(hoverId);
  if(rec.d===d){ delete rec.d; } else { rec.d=d; rec.t=new Date().toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"}); }
  setRec(hoverId,rec); render();
});
document.addEventListener("click", ev=>{
  const chip=ev.target.closest(".chip");
  if(chip){ filt[chip.dataset.k]=chip.dataset.v; render(); return; }
  const btn=ev.target.closest(".d-btn");
  if(btn){
    const card=btn.closest(".card"), id=card.dataset.id;
    const d=["accept","pending","reject"].find(x=>btn.classList.contains(x));
    const rec=getRec(id);
    if(rec.d===d){ delete rec.d; } else { rec.d=d; rec.t=new Date().toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"}); }
    setRec(id,rec); render(); return;
  }
});
document.addEventListener("input", ev=>{
  if(ev.target.id==="q"){ filt.q=ev.target.value; render(); return; }
  if(ev.target.classList.contains("note")){
    const id=ev.target.closest(".card").dataset.id;
    const rec=getRec(id); rec.n=ev.target.value;
    setRec(id,rec);
  }
});

$("exportJson").onclick=()=>{
  const c=counts();
  const out={ exported_at:new Date().toISOString(), tool:"cloudra-easy-review",
    target:30, counts:c, decisions:{} };
  DATA.forEach(e=>{ const r=getRec(e.id);
    if(r.d||r.n) out.decisions[e.id]={decision:r.d||null, note:r.n||"",
      name:e.name, role:e.role, verify:e.status}; });
  const blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="easy_review_decisions_"+new Date().toISOString().slice(0,10)+".json";
  a.click(); URL.revokeObjectURL(a.href);
  toast(`已导出：收录 ${c.accept}｜待定 ${c.pending}｜排除 ${c.reject}`);
};
$("copyList").onclick=()=>{
  const acc=DATA.filter(e=>getRec(e.id).d==="accept").map(e=>e.id);
  const txt = acc.join(", ");
  const done=()=>toast(txt?`已复制 ${acc.length} 个入选编号`:"尚无收录标记");
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(done).catch(()=>{promptFb(txt);done();});
  } else { promptFb(txt); done(); }
  function promptFb(t){ const w=window.open("","_blank");
    if(w){w.document.write("<pre style='font-size:16px'>"+(t||"（无）")+"</pre>");} }
};
$("importJson").onchange=ev=>{
  const f=ev.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>{ try{
      const obj=JSON.parse(rd.result);
      const dec=obj.decisions||obj;
      let n=0;
      Object.entries(dec).forEach(([id,v])=>{
        if(DATA.some(e=>e.id===id)){ state[id]={...(state[id]||{}),
          ...(v.decision?{d:v.decision}:{}), ...(v.note?{n:v.note}:{})}; n++; }
      });
      localStorage.setItem(KEY,JSON.stringify(state)); render();
      toast(`已导入 ${n} 条标记`);
    }catch(e){ toast("导入失败：不是合法的导出 JSON"); } };
  rd.readAsText(f); ev.target.value="";
};

render();
</script>
</body>
</html>
"""


def main():
    entries = parse()
    assert len(entries) == 29, f"expected 29 entries, got {len(entries)}"
    assert {e["id"] for e in entries} >= set(SHORTLIST + ALTERNATES)
    rdkit_check(entries)
    today = datetime.date.today().isoformat()
    payload = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__PAYLOAD__", payload).replace("__GEN_DATE__", today)
    out = BASE / "easy_review.html"
    out.write_text(html, encoding="utf-8")
    print("written:", out, f"{out.stat().st_size/1024:.1f} KB")
    from collections import Counter
    print("groups:", dict(Counter(e["group"] for e in entries)))
    print("verify:", dict(Counter(e["status"] for e in entries)))
    print("roles:", dict(Counter(e["role"] for e in entries)))


if __name__ == "__main__":
    main()
