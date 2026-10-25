"""2D 分子图按表面明暗调整中性色，元素颜色由 RDKit 保留。"""

from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloudra.services.api_v2.routers import chem


@pytest.fixture
def client():
    chem._render_smiles_to_svg.cache_clear()
    app = FastAPI()
    app.include_router(chem.build_router(SimpleNamespace(protected=[])))
    with TestClient(app) as test_client:
        yield test_client
    chem._render_smiles_to_svg.cache_clear()


@pytest.mark.parametrize("theme,neutral", [("light", "#000000"), ("dark", "#cbd5e1")])
def test_render_keeps_element_colors_and_transparent_background(client, rdkit_chemistry, theme, neutral):
    response = client.get("/api/v2/chem/render-smiles", params={"smiles": "CCNO", "theme": theme})

    assert response.status_code == 200
    root = ElementTree.fromstring(response.text)
    # 暗色补丁曾覆盖所有 bond-* 路径，导致带元素颜色的键段也变成同一种灰色。
    assert not root.findall("{http://www.w3.org/2000/svg}style")
    colors = {
        entry.split(":", 1)[1].lower()
        for path in root.findall("{http://www.w3.org/2000/svg}path")
        if "bond-" in path.attrib.get("class", "")
        for entry in path.attrib.get("style", "").split(";")
        if entry.startswith("stroke:")
    }
    assert colors == {neutral, "#0000ff", "#ff0000"}
    assert not root.findall("{http://www.w3.org/2000/svg}rect")


@pytest.mark.parametrize("theme,color", [("light", "#475569"), ("dark", "#94a3b8")])
@pytest.mark.parametrize("source", ["empty", "invalid", "unavailable"])
def test_fallback_uses_readable_theme_text(client, monkeypatch, theme, color, source):
    smiles = " " if source == "empty" else "<not a molecule>"
    if source == "unavailable":
        monkeypatch.setattr(chem, "_RDKIT_AVAILABLE", False)
    response = client.get("/api/v2/chem/render-smiles", params={"smiles": smiles, "theme": theme})

    assert response.status_code == 200
    root = ElementTree.fromstring(response.text)
    assert root.find("{http://www.w3.org/2000/svg}rect").attrib["fill"] == "transparent"
    text = root.find("{http://www.w3.org/2000/svg}text")
    assert text.attrib["fill"] == color
    assert text.text == ("(empty)" if source == "empty" else smiles)
