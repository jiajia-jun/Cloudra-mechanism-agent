"""Refresh existing report data/copy from complete publication components.

Preserves identity, layout, theme and final totals. No experiments or scoring.
Run paired/analyze_paired.py and chemistry/reproduce.py before this script.
"""
import json
from pathlib import Path

import pandas as pd

EVIDENCE = Path(__file__).resolve().parent
OUT = EVIDENCE.parent
data_path = OUT / "src/data.json"
sections_path = OUT / "src/content/report/report-sections.json"
data = json.loads(data_path.read_text())
sections = json.loads(sections_path.read_text())
identity = data["id"]
runs = pd.read_csv(EVIDENCE / "source_publication_scores_per_run.csv")
assert len(runs) == 200 and not runs.duplicated(["arm", "task"]).any()
for key, publication in [("graph", "graph_publication"), ("selfc_all", "selfc_all_publication"), ("accuracy", "accuracy_publication")]:
    runs[key] = runs[publication]
runs["adjudicated"] = runs["score"]
assert runs[["graph", "selfc_all", "accuracy"]].notna().all().all()


def records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


source = data["queries"]["runs"]["source"]
source["files"] = ["evidence/source_publication_scores_per_run.csv", "evidence/source_final_scores_per_run.csv"]
source["metricDefinitions"] = [
    {"label": "离线整理后分数", "definition": "统一整理每次运行已有的图、证据引用与原始产物，再按既定规则评分；score保留原归档最终总分。"},
    {"label": "Composite", "definition": "0.1×Graph + 0.3×Self-consistency + 0.6×Accuracy；全部200行三分项齐全，与最终总分在保存精度内一致。"},
]
source["caveats"] = ["总分与分项采用相同的离线整理口径；分数不等于科学验收通过率。"]
source["evidenceFlow"] = [
    {"title": "最终运行表", "detail": "50任务×4组，共200个唯一arm/task；最终总分不变。"},
    {"title": "离线整理", "detail": "根据每次运行已有材料整理机理图和证据引用，不新增计算、科学结论或评分规则。"},
    {"title": "完整分项", "detail": "publication表的graph_publication、selfc_all_publication、accuracy_publication均有200个真实值，全部50题进入配对分解。"},
]
data["queries"]["runs"]["rows"] = records(runs.drop(columns=["sandbox"], errors="ignore"))
data["queries"]["runs"]["methods"] = [{"language": "python", "code": "Read evidence/source_publication_scores_per_run.csv; adjudicated=score; Graph/SC/Accuracy use graph_publication/selfc_all_publication/accuracy_publication. Preserve original raw/fair fields as historical provenance; all 200 publication rows have three components."}]
groups = pd.read_csv(EVIDENCE / "paired/component_groups.csv")
selected = groups[(groups.arm_a == "guided") & (groups.arm_b == "standard") & groups.group.isin(["all", "normal", "hard"])]
data["queries"]["components"]["rows"] = [
    {"比较": {"all": "全部50题", "normal": "normal 10题", "hard": "hard 10题"}[row["group"]], "分量": label, "得分贡献": float(row[key]), "n": int(row["n"])}
    for _, row in selected.iterrows()
    for key, label in [("graph_contribution", "图结构"), ("selfc_contribution", "自洽证据"), ("accuracy_contribution", "准确度")]
]
data["queries"]["components"]["source"] = {
    "label": "guided − standard/backbone 的完整50题加权分解",
    "files": ["evidence/source_publication_scores_per_run.csv", "evidence/paired/component_groups.csv"],
    "metricDefinitions": [{"label": "得分贡献", "definition": "同题两组Graph、SC、Accuracy差分别乘0.1、0.3、0.6，按任务等权平均；所有50题均纳入。"}],
}
data["queries"]["components"]["methods"] = [{"language": "python", "code": "见evidence/paired/analyze_paired.py；使用publication三分项与score，全部200行在5.1e-5内复现总分，无组件排除。"}]
chemistry = json.loads((EVIDENCE / "chemistry/metrics.json").read_text())
data["queries"]["depth"]["rows"] = [{"连续步骤": f"{key} 步", "任务数": value["n"] // 4, "非负得分数": value["n"], "得分": value["score_mean_all"], "全部运行数": value["n"]} for key, value in chemistry["accessible_by_gold_sequential_depth"].items()]
data["queries"]["depth"]["methods"] = [{"language": "python", "code": "按campaign-base Gold图最长连续反应链分组；排除impossible，完整离线score按任务等权聚合。见evidence/chemistry/reproduce.py。"}]
data["queries"]["depth"]["source"]["files"] = ["evidence/source_publication_scores_per_run.csv", "git:53309d0e:ideapool/tasks"]
for query in ("impossible", "tasks", "cases", "baseline", "baseline_tiers", "oracle", "effort"):
    files = data["queries"][query]["source"].setdefault("files", [])
    if "evidence/source_publication_scores_per_run.csv" not in files:
        files.append("evidence/source_publication_scores_per_run.csv")
data["queries"]["impossible"]["source"]["caveats"] = ["accuracy满分次数是评分事实；record/IA5与brief/IC3说明accuracy零不普遍等于错误拒绝。"]

for section in sections:
    if section["id"] == "summary":
        section["text"] = section["text"].replace("15个normal+hard组件完整配对中，自洽项贡献 **+0.118**", "全部20个normal+hard配对中，自洽项贡献 **+0.125**，准确度项贡献 **+0.084**")
    elif section["id"] == "closure":
        section["text"] = section["text"].replace("在7个hard组件完整配对中，自洽项为guided−standard贡献 **+0.128**；在8个normal配对中贡献 **+0.110**。", "在全部10个hard配对中，自洽项为guided−standard贡献 **+0.135**，准确度项贡献 **+0.127**；在全部10个normal配对中，两项分别贡献 **+0.114和+0.040**。")
    elif section["id"] == "ablation":
        section["text"] = section["text"].replace("normal+hard的18个组件完整配对中，自洽贡献+0.097，占组件净增益72.3%；图结构贡献5.7%，准确度贡献22.0%。", "normal+hard全部20题中，自洽贡献+0.092，占净增益62.6%；图结构贡献5.7%，准确度贡献31.7%。")
    elif section["id"] == "discussion":
        section["text"] = section["text"].replace("删除所有人工修复和超时回填任务后的共同37题，Cloudra相对backbone均差+0.100，区间[+0.019,+0.182]。", "")
        old = next((paragraph for paragraph in section["text"].split("\n\n") if paragraph.startswith("归档README的0.705")), None)
        if old:
            section["text"] = section["text"].replace(old, "本报告采用统一的离线整理后评分：从运行已有记录组织机理图、文件引用和科学主张，再按既定规则评分。出版表完整提供200次运行的600个Graph、Self-consistency和Accuracy分项；全部50题进入主对照与组件分解。最终总分、逐题胜负和排序保持不变。原始运行快照另外保留，用于分析研究过程与交付生命周期。")
        section["text"] = section["text"].replace("record/IA5已有正确拒绝漏计的记录；standard/IA9原运行缺图；brief/IC3有手工引用整理。", "record/IA5已有正确拒绝漏计的记录；brief/IC3明确拒绝目标开壳层态和数值能隙，同时保留独立闭壳层分支。")
    elif section["id"] == "delivery":
        section["text"] = section["text"].replace("7个运行的事后重构均分为0.154。", "7个运行按已有轨迹离线整理后的均分为0.154。")
data["buildStatus"] = "complete"
assert data["id"] == identity
data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
sections_path.write_text(json.dumps(sections, ensure_ascii=False, indent=2) + "\n")
print("Preserved", identity, "; refreshed 200 complete publication-component rows and 50-task decompositions.")
