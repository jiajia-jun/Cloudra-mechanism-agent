"""Missing IRC evidence must not be confused with a completed calculation."""

from pathlib import Path

import pytest

from cloudra.tools.core.gaussian_frames import extract_irc


@pytest.mark.parametrize(
    ("termination", "diagnosis"),
    [
        ("", "native normal termination is absent"),
        ("Error termination via Lnk1e", "native error termination"),
        ("Normal termination of Gaussian 16", "normally terminated but IRC evidence is incomplete"),
        (
            "Normal termination of Gaussian 16\nError termination via Lnk1e",
            "native error termination",
        ),
    ],
)
def test_missing_gaussian_irc_summary_reports_native_calculation_state(tmp_path, termination, diagnosis):
    log = tmp_path / "irc.log"
    log.write_text(f" # irc=(calcfc,maxpoint=10) hf/sto-3g\n{termination}\n")

    with pytest.raises(ValueError) as error:
        extract_irc(str(log))

    message = str(error.value).lower()
    assert diagnosis.lower() in message
    assert "summary of reaction path following" in message


def test_step_limited_but_complete_gaussian_irc_retains_its_endpoint_evidence():
    log = Path(__file__).parent / "fixtures" / "gaussian" / "hcn_ts_irc_g16.log"
    frames, meta = extract_irc(str(log))

    assert any(frame.xyz and frame.reaction_coordinate < 0 for frame in frames)
    assert any(frame.xyz and frame.reaction_coordinate > 0 for frame in frames)
    assert not (meta["forward_converged"] and meta["backward_converged"])
