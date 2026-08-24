#!/usr/bin/env python3
"""Generate selection.html — interactive screening page for the four-tier
benchmark literature pool.

Data flow: abstracts/titles/candidates come verbatim from the four tier
metadata.json files; scores/bands/reasons are imported from _gen_selection.py
(single source of truth, consistent with SELECTION.md). The page is a single
self-contained HTML file: vanilla JS, localStorage persistence, JSON export.
"""
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import _gen_selection as G  # noqa: E402  (REC / overall / badge / clean ...)


def load(tier):
    return json.loads((BASE / tier / "metadata.json").read_text(encoding="utf-8"))


def build_entries():
    entries = []
    for tier in G.TIER_ORDER:
        for e in load(tier):
            eid = e["id"]
            sc = G.overall(eid)
            fit, dat, val, acc, reason = G.REC[eid]
            entries.append({
                "id": eid,
                "tier": tier,
                "title": G.clean(e.get("title") or ""),
                "authors": e.get("authors", []),
                "year": e.get("year"),
                "venue": G.clean(e.get("venue") or ""),
                "doi": e.get("doi") or "",
                "url": e.get("url") or "",
                "oa_status": e.get("oa_status", ""),
                "pdf_file": e.get("pdf_file") or "",
                "already_held": str(e["already_held"]) if e.get("already_held") else "",
                "abstract": G.clean(e.get("abstract") or ""),
                "cands": [G.clean(c) for c in e.get("candidate_reactions", [])],
                "fit": fit, "dat": dat, "val": val, "acc": acc,
                "overall": sc,
                "band": G.badge(sc),
                "reason": reason,
            })
    # tier order preserved, overall descending within each tier (same as SELECTION.md)
    entries.sort(key=lambda x: (G.TIER_ORDER.index(x["tier"]), -x["overall"]))
    return entries


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>四级测试集候选文献打标台</title>
<style>
:root{
  --bg:#f6f7f9; --card:#fff; --ink:#1c2330; --muted:#6b7280; --line:#e5e7eb;
  --easy:#16a34a; --normal:#2563eb; --hard:#ea580c; --impossible:#9333ea;
  --accept:#16a34a; --reject:#dc2626; --pend:#d97706;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
  "Hiragino Sans GB","Microsoft YaHei",sans-serif}
a{color:#2563eb;text-decoration:none} a:hover{text-decoration:underline}
.topbar{position:sticky;top:0;z-index:10;background:#ffffffee;
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 20px 8px}
.topbar h1{font-size:17px;margin:0 0 2px}
.topbar .sub{font-size:12px;color:var(--muted)}
.counts{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-top:6px;font-weight:600}
.counts .c{display:inline-flex;align-items:center;gap:4px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.bar{height:4px;background:var(--line);border-radius:2px;margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;background:#2563eb;width:0%;transition:width .25s}
.controls{max-width:960px;margin:12px auto;padding:0 16px;display:flex;
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
main{max-width:960px;margin:0 auto;padding:4px 16px 80px}
.sechead{margin:26px 0 10px;font-size:15px;font-weight:700;display:flex;
  align-items:center;gap:8px}
.sechead .t-dot{width:11px;height:11px;border-radius:3px}
.sechead .cnt{font-size:12px;color:var(--muted);font-weight:400}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px 12px;margin-bottom:12px;border-left:4px solid var(--line)}
.card.t-easy{border-left-color:var(--easy)} .card.t-normal{border-left-color:var(--normal)}
.card.t-hard{border-left-color:var(--hard)} .card.t-impossible{border-left-color:var(--impossible)}
.card.d-accept{background:#f0fdf4;border-color:#bbf7d0}
.card.d-reject{opacity:.55;background:#fafafa}
.card.d-pending{background:#fffbeb;border-color:#fde68a}
.cardhead{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px}
.tid{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;
  background:#eef1f5;border-radius:5px;padding:1px 7px}
.score{font-size:13px;font-weight:700}
.band{font-size:11px;border-radius:5px;padding:1px 7px;font-weight:600}
.band.b-must{background:#dcfce7;color:#166534} .band.b-rec{background:#dbeafe;color:#1e40af}
.band.b-alt{background:#f3f4f6;color:#4b5563}
.pdftag{font-size:11px;color:var(--muted)}
.pdftag a{font-weight:600}
.card h3{font-size:15.5px;margin:3px 0 2px;line-height:1.45}
.meta{font-size:12.5px;color:var(--muted)}
.subs{font-size:12px;color:#475569;margin-top:4px}
.subs b{color:var(--ink)}
details{margin-top:7px;border-top:1px dashed var(--line);padding-top:6px}
summary{cursor:pointer;font-size:12.5px;color:#2563eb;user-select:none}
details p,details ul{font-size:13px;margin:6px 0 2px;color:#333}
details li{margin-bottom:3px}
.reason{font-size:12.5px;background:#f8fafc;border-radius:8px;
  padding:6px 10px;margin-top:8px;color:#334155}
.decide{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
.d-btn{border:1.5px solid var(--line);background:#fff;border-radius:8px;
  padding:5px 13px;font-size:13px;cursor:pointer;font-weight:600}
.d-btn.accept:hover,.d-btn.accept.on{background:var(--accept);color:#fff;border-color:var(--accept)}
.d-btn.reject:hover,.d-btn.reject.on{background:var(--reject);color:#fff;border-color:var(--reject)}
.d-btn.pending:hover,.d-btn.pending.on{background:var(--pend);color:#fff;border-color:var(--pend)}
.note{flex:1;min-width:140px;border:1px solid var(--line);border-radius:8px;
  padding:5px 10px;font-size:12.5px}
.saved{font-size:11px;color:var(--muted)}
.toast{position:fixed;left:50%;bottom:30px;transform:translateX(-50%);
  background:#1c2330;color:#fff;border-radius:8px;padding:8px 18px;
  font-size:13px;opacity:0;transition:opacity .25s;pointer-events:none;z-index:99}
.toast.show{opacity:.95}
footer{max-width:960px;margin:30px auto;padding:0 16px 40px;
  font-size:12px;color:var(--muted)}
@media print{.controls,.decide,.topbar{display:none}}
</style>
</head>
<body>
<div class="topbar">
  <h1>四级测试集候选文献打标台</h1>
  <div class="sub">数据来源 ideapool/benchmark_literature/{easy,normal,hard,impossible}/metadata.json 共 __TOTAL__ 篇｜生成于 __GEN_DATE__｜打标自动保存在本浏览器 localStorage，换设备请先「导出JSON」再在目标机器「导入」</div>
  <div class="counts" id="counts"></div>
  <div class="bar"><i id="pbar"></i></div>
</div>
<div class="controls">
  <span id="tierChips"></span>
  <span style="width:1px;height:22px;background:var(--line)"></span>
  <span id="statusChips"></span>
  <input class="search" id="q" type="search" placeholder="搜索标题 / 编号 / 摘要关键词…">
  <button class="btn" id="toggleAbs">展开全部摘要</button>
  <button class="btn primary" id="exportJson">⬇ 导出JSON</button>
  <button class="btn" id="copyList">📋 复制入选清单</button>
  <label class="btn" style="position:relative;overflow:hidden">导入
    <input type="file" id="importJson" accept=".json" style="position:absolute;inset:0;opacity:0;cursor:pointer">
  </label>
</div>
<main id="list"></main>
<footer>
  <b>使用说明</b>：每篇文献下方三个按钮决定收录与否，再次点击同一按钮可取消标记；备注随打标实时保存。筛选完成后点「⬇ 导出JSON」存档，或「📋 复制入选清单」把编号列表直接粘贴回对话即可。<br>
  分项评分口径：综合分 = 体系适配×0.30 + 参考数据×0.25 + 测试价值×0.30 + 可获取性×0.15（各 0–10）；≥8.5 必选、7.5–8.4 推荐、&lt;7.5 备选。与 SELECTION.md 同源同值。
</footer>
<div class="toast" id="toast"></div>

<script>
const DATA = __PAYLOAD__;
const KEY = "cloudra_bench_sel_v1";
const TIERS = ["easy","normal","hard","impossible"];
const TIER_LABEL = {easy:"Easy 单步",normal:"Normal 多步",hard:"Hard 立体化学",impossible:"Impossible 多参考"};
const STATUS = ["all","untagged","accept","pending","reject"];
const STATUS_LABEL = {all:"全部",untagged:"未标",accept:"✅ 收录",pending:"⏸ 待定",reject:"❌ 排除"};

function loadState(){ try{return JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){return {}} }
let state = loadState();
let filt = {tier:"all", status:"all", q:""};
let absOpen = false;

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

function pdfTag(e){
  if(e.pdf_file) return `<span class="pdftag">✅ <a href="${e.tier}/${esc(e.pdf_file)}" target="_blank">PDF 在手</a></span>`;
  if(e.already_held) return `<span class="pdftag">📚 本地已有：${esc(e.already_held)}</span>`;
  const oa = esc(e.oa_status||"");
  return `<span class="pdftag">🔒 无 PDF（${oa==="closed"?"付费墙":oa}）</span>`;
}
function linkOf(e){
  if(e.doi) return `https://doi.org/${esc(e.doi)}`;
  return esc(e.url||"#");
}
function authorsShort(a){
  const s=a.slice(0,3).join(", "); return a.length>3 ? s+" et al." : s;
}
function bandClass(b){ return b==="必选"?"b-must":(b==="推荐"?"b-rec":"b-alt"); }

function cardHtml(e){
  const r=getRec(e.id), d=r.d||"", note=r.n||"";
  return `<article class="card t-${e.tier} ${d?("d-"+d):""}" data-id="${e.id}">
    <div class="cardhead">
      <span class="tid">${e.id}</span>
      <span class="score">★ ${e.overall}</span>
      <span class="band ${bandClass(e.band)}">${e.band}</span>
      <span class="pdftag">${TIER_LABEL[e.tier]}</span>
      ${pdfTag(e)}
      <span style="flex:1"></span>
      <span class="saved">${r.t?("已保存 "+r.t):""}</span>
    </div>
    <h3><a href="${linkOf(e)}" target="_blank">${esc(e.title)}</a></h3>
    <div class="meta">${esc(authorsShort(e.authors))} ｜ ${esc(String(e.year))} ｜ ${esc(e.venue)}</div>
    <div class="subs">体系适配 <b>${e.fit}</b> ｜ 参考数据 <b>${e.dat}</b> ｜ 测试价值 <b>${e.val}</b> ｜ 可获取 <b>${e.acc}</b>　→　综合 <b>${e.overall}</b></div>
    <details class="abs"${absOpen?" open":""}><summary>摘要</summary><p>${esc(e.abstract)}</p></details>
    <details${absOpen?" open":""}><summary>候选反应标注（${e.cands.length}）</summary>
      <ul>${e.cands.map(c=>`<li>${esc(c)}</li>`).join("")}</ul></details>
    <div class="reason">💡 ${esc(e.reason)}</div>
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
  $("counts").innerHTML =
    `<span class="c"><span class="dot" style="background:#1c2330"></span>总数 ${total}</span>`+
    `<span class="c"><span class="dot" style="background:var(--accept)"></span>收录 ${c.accept}</span>`+
    `<span class="c"><span class="dot" style="background:var(--pend)"></span>待定 ${c.pending}</span>`+
    `<span class="c"><span class="dot" style="background:var(--reject)"></span>排除 ${c.reject}</span>`+
    `<span class="c"><span class="dot" style="background:#cbd5e1"></span>未标 ${c.untagged}</span>`+
    `<span class="c" style="color:var(--muted);font-weight:400">目标题量 100（Easy30/Normal30/Hard20/Impossible20）</span>`;
  $("pbar").style.width=(tagged/total*100).toFixed(1)+"%";

  // chips
  $("tierChips").innerHTML=[["all","全部"]].concat(TIERS.map(t=>[t,TIER_LABEL[t]]))
    .map(([v,l])=>{ const n=v==="all"?total:DATA.filter(e=>e.tier===v).length;
      return `<button class="chip ${filt.tier===v?"on":""}" data-k="tier" data-v="${v}">${l}<span class="n">${n}</span></button>`;}).join("");
  const st=counts();
  $("statusChips").innerHTML=STATUS.map(v=>{
    const n=v==="all"?total:st[v];
    return `<button class="chip ${filt.status===v?"on":""}" data-k="status" data-v="${v}">${STATUS_LABEL[v]}<span class="n">${n}</span></button>`;}).join("");

  // list
  const q=filt.q.trim().toLowerCase();
  let html="", shown=0;
  TIERS.filter(t=>filt.tier==="all"||filt.tier===t).forEach(t=>{
    const es=DATA.filter(e=>e.tier===t &&
      (filt.status==="all" || (filt.status==="untagged"?!getRec(e.id).d:getRec(e.id).d===filt.status)) &&
      (!q || (e.id+" "+e.title+" "+e.abstract+" "+e.reason+" "+e.venue).toLowerCase().includes(q)));
    if(!es.length) return;
    shown+=es.length;
    const np=es.filter(e=>e.pdf_file).length;
    html+=`<div class="sechead"><span class="t-dot" style="background:var(--${t})"></span>${TIER_LABEL[t]}
      <span class="cnt">${es.length} 篇｜PDF ${np}｜标题量目标 ${{easy:30,normal:30,hard:20,impossible:20}[t]}</span></div>`;
    html+=es.map(cardHtml).join("");
  });
  $("list").innerHTML = shown ? html :
    `<p style="color:var(--muted);text-align:center;margin-top:60px">没有符合当前筛选条件的文献。</p>`;
}

// ---- events ----
document.addEventListener("click", ev=>{
  const chip=ev.target.closest(".chip");
  if(chip){ filt[chip.dataset.k]=chip.dataset.v; render(); return; }
  const btn=ev.target.closest(".d-btn");
  if(btn){
    const card=btn.closest(".card"), id=card.dataset.id;
    const map={"accept":"accept","pending":"pending","reject":"reject"};
    const d=map[btn.className.split(" ").find(c=>map[c])];
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
$("toggleAbs").onclick=()=>{ absOpen=!absOpen;
  document.querySelectorAll("details").forEach(d=>d.open=absOpen);
  $("toggleAbs").textContent=absOpen?"收起全部摘要":"展开全部摘要"; };

$("exportJson").onclick=()=>{
  const c=counts();
  const out={ exported_at:new Date().toISOString(), tool:"cloudra-benchmark-screening",
    counts:c, decisions:{} };
  DATA.forEach(e=>{ const r=getRec(e.id);
    if(r.d||r.n) out.decisions[e.id]={decision:r.d||null, note:r.n||"",
      title:e.title, tier:e.tier, overall:e.overall}; });
  const blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="selection_decisions_"+new Date().toISOString().slice(0,10)+".json";
  a.click(); URL.revokeObjectURL(a.href);
  toast(`已导出：收录 ${c.accept}｜待定 ${c.pending}｜排除 ${c.reject}`);
};

$("copyList").onclick=()=>{
  const acc=DATA.filter(e=>getRec(e.id).d==="accept").map(e=>e.id);
  const txt = acc.length ? acc.join(", ") : "";
  const done=()=>toast(txt?`已复制 ${acc.length} 个入选编号`:"尚无收录标记");
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(done).catch(()=>{promptFallback(txt);done();});
  } else { promptFallback(txt); done(); }
  function promptFallback(t){ const w=window.open("","_blank");
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
    entries = build_entries()
    today = datetime.date.today().isoformat()
    payload = json.dumps(entries, ensure_ascii=False).replace("</", "<\\/")  # safe inside <script>; JS expects a plain array
    html = (
        TEMPLATE
        .replace("__PAYLOAD__", payload)
        .replace("__TOTAL__", str(len(entries)))
        .replace("__GEN_DATE__", today)
    )
    out = BASE / "selection.html"
    out.write_text(html, encoding="utf-8")
    print("written:", out, f"{out.stat().st_size/1024:.1f} KB")
    print("entries:", len(entries))
    for t in G.TIER_ORDER:
        es = [e for e in entries if e["tier"] == t]
        print(f"  {t}: n={len(es)} pdf={sum(1 for e in es if e['pdf_file'])} "
              f"cands={sum(len(e['cands']) for e in es)}")


if __name__ == "__main__":
    main()
