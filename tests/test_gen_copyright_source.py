"""The local registration generator must work without tracked output folders."""

from scripts import gen_copyright_source


def test_generator_creates_missing_output_directories(tmp_path, monkeypatch):
    materials = tmp_path / "materials"
    monkeypatch.setattr(gen_copyright_source, "MATERIALS", materials)
    monkeypatch.setattr(gen_copyright_source, "LINES_PER_PAGE", 2)
    monkeypatch.setattr(gen_copyright_source, "PAGES_PER_FILE", 1)
    monkeypatch.setattr(
        gen_copyright_source,
        "collect_lines",
        lambda: [("cloudra/sample.py", i, f"value_{i} = {i}") for i in range(1, 5)],
    )
    compiled = []
    monkeypatch.setattr(gen_copyright_source, "compile_tex", compiled.append)

    gen_copyright_source.main()

    expected = {
        "01_源代码/源代码_前30页.txt",
        "01_源代码/源代码_后30页.txt",
        "05_完整申请文件包/02_源程序_前30页_排版.txt",
        "05_完整申请文件包/03_源程序_后30页_排版.txt",
        "06_LaTeX排版/01_源程序_前30页.tex",
        "06_LaTeX排版/02_源程序_后30页.tex",
    }
    assert {str(path.relative_to(materials)) for path in materials.rglob("*") if path.is_file()} == expected
    assert len(compiled) == 2
    assert all(path.is_file() for path in compiled)
    first = materials / "01_源代码/源代码_前30页.txt"
    copy = materials / "05_完整申请文件包/02_源程序_前30页_排版.txt"
    assert first.read_bytes() == copy.read_bytes()
    gen_copyright_source.main()
    assert first.read_bytes() == copy.read_bytes()
