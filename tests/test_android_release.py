from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.android_build import audit_apk_signature


def _result(subject: str, fingerprint: str = "ab" * 32):
    return SimpleNamespace(
        returncode=0,
        stdout=(
            "Verifies\n"
            "Verified using v2 scheme (APK Signature Scheme v2): true\n"
            f"Signer #1 certificate DN: {subject}\n"
            f"Signer #1 certificate SHA-256 digest: {fingerprint}\n"
        ),
        stderr="",
    )


def test_release_audit_requires_pinned_non_debug_certificate(tmp_path, monkeypatch):
    apk = tmp_path / "cloudra.apk"
    apk.write_bytes(b"apk")
    monkeypatch.setattr(
        "cloudra.android_build.subprocess.run",
        lambda *_args, **_kwargs: _result("CN=Cloudra Release"),
    )
    result = audit_apk_signature(
        apk, expected_cert_sha256="AB:" * 31 + "AB", apksigner="apksigner"
    )
    assert result["certificate_sha256"] == "ab" * 32
    assert result["signature_schemes"][2] is True

    with pytest.raises(RuntimeError, match="pinned"):
        audit_apk_signature(apk, apksigner="apksigner")


def test_release_audit_rejects_debug_certificate(tmp_path, monkeypatch):
    apk = tmp_path / "cloudra.apk"
    apk.write_bytes(b"apk")
    monkeypatch.setattr(
        "cloudra.android_build.subprocess.run",
        lambda *_args, **_kwargs: _result("CN=Android Debug,O=Android,C=US"),
    )
    with pytest.raises(RuntimeError, match="Debug"):
        audit_apk_signature(
            apk, expected_cert_sha256="ab" * 32, apksigner="apksigner"
        )
