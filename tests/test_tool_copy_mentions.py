import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IN_PROMPTS = re.compile(
    r"\b(text_reader|image_reader|pdf2md|pdf2image|paper_searcher|"
    r"openalex_searcher|bashtools|text_writer|edit_file|getskill|"
    r"web_fetcher|headless_browser|DurationSeconds)\b"
)

def test_prompts_use_new_tool_names():
    hits = []
    for path in (ROOT / "cloudra" / "prompts").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_IN_PROMPTS.search(text):
            hits.append(path.name)
    assert hits == []

def test_schedule_stage_uses_real_fields():
    text = (ROOT / "cloudra/runtime_v2/policies/schedule_stage.py").read_text(encoding="utf-8")
    assert "DurationSeconds" not in text
    assert "delay_seconds" in text
    assert "message" in text
