from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOP = (
    ROOT
    / "cloudra"
    / "skills"
    / "dft-calculation"
    / "references"
    / "mechanism-elucidation-sop.md"
)
SKILL = ROOT / "cloudra" / "skills" / "dft-calculation" / "SKILL.md"
PERICYCLIC = SOP.parent / "mechanisms" / "pericyclic.md"
COORDINATOR = ROOT / "cloudra" / "prompts" / "coordinator.md"


def test_claisen_worked_example_defines_dag_evidence_contract() -> None:
    text = SOP.read_text(encoding="utf-8")

    assert "C=COCC=C" in text and "C=CCCC=O" in text
    assert "process DAG" in text and "delivery DAG" in text
    assert all(mode in text for mode in ("standard", "dag_record", "dag_guided"))
    assert "endpoint-supported" in text
    assert "short bidirectional IRC" in text
    assert "optimized endpoint" in text
    assert "ts_guess" in text and "不能" in text
    assert "指针" in text


def test_agent_entry_points_route_dag_sessions_to_the_worked_sop() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    pericyclic = PERICYCLIC.read_text(encoding="utf-8")
    coordinator = COORDINATOR.read_text(encoding="utf-8")

    assert "DAG-guided" in skill and "mechanism-elucidation-sop.md" in skill
    assert "Claisen" in pericyclic and "delivery DAG" in pericyclic
    assert "DAG orchestration" in coordinator
    assert "init_from_template" in coordinator
    assert "delivery_report" in coordinator
    assert "Supervisor" in coordinator
