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
PERICYCLIC = ROOT / "cloudra" / "skills" / "reaction-mechanisms" / "references" / "pericyclic.md"
COORDINATOR = ROOT / "cloudra" / "prompts" / "coordinator.md"
SUPERVISOR = ROOT / "cloudra" / "prompts" / "supervisor.md"


def test_claisen_worked_example_defines_dag_evidence_contract() -> None:
    text = SOP.read_text(encoding="utf-8")

    assert "C=COCC=C" in text and "C=CCCC=O" in text
    assert "系统仅有 **delivery DAG**" in text and "不存在 process DAG" in text
    assert all(mode in text for mode in ("standard", "dag_record", "dag_guided"))
    assert "endpoint-supported" in text
    assert "short bidirectional IRC" in text or "短程双向 IRC" in text
    assert "optimized endpoint" in text
    assert "ts_guess" in text and "不能" in text
    assert "指针" in text


def test_agent_entry_points_route_dag_sessions_to_the_worked_sop() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    pericyclic = PERICYCLIC.read_text(encoding="utf-8")
    coordinator = COORDINATOR.read_text(encoding="utf-8")

    assert "DAG-guided" in skill and "mechanism-elucidation-sop.md" in skill
    assert "Claisen" in pericyclic and "delivery DAG" in pericyclic
    assert "In DAG mode" in coordinator
    assert "dag_propose_mechanism" in coordinator
    assert "delivery_report" in coordinator
    assert "Supervisor" in coordinator
    assert "Considered" in coordinator and "Observed" in coordinator and "Chose" in coordinator
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    assert "A single-path proposal can be accepted" in supervisor
    assert "the user's scope or the rationale supports that choice" in supervisor
    assert "an unexplained omission needs revision" in supervisor
