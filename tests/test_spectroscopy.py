import pytest
import os
from cloudra.tools.Chemtool.ir_processor import IRProcessor, IRProcessor_input_schema
from cloudra.tools.Chemtool.nmr_processor import NMRProcessor, NMRProcessor_input_schema

@pytest.fixture
def mock_ir_file(tmp_path):
    # 构造一个在 1720 有明显峰的数据集
    dx_content = """##TITLE=Test IR
##JCAMP-DX=5.01
##DATA TYPE=INFRARED SPECTRUM
##DATA CLASS=XYDATA
##XUNITS=1/CM
##YUNITS=ABSORBANCE
##XFACTOR=1
##YFACTOR=1
##FIRSTX=4000
##LASTX=600
##NPOINTS=11
##FIRSTY=0.05
##XYDATA=(X++(Y..Y))
4000 0.05
3400 0.10
3000 0.05
2000 0.05
1800 0.10
1740 0.50
1720 0.90
1700 0.50
1600 0.10
1000 0.05
600 0.10
##END="""
    dx_file = tmp_path / "test.dx"
    dx_file.write_text(dx_content)
    return str(dx_file)

@pytest.mark.asyncio
async def test_ir_processor_basic(mock_ir_file, mock_session):
    """测试红外解析器的基本功能和高级参数。"""
    tool = IRProcessor()
    input_data = IRProcessor_input_schema(
        data_path=mock_ir_file,
        smooth=False, 
        baseline=False, # 关闭基线校正以简化 mock 数据的峰检测
        peak_threshold=0.1,
        advanced_settings={}
    )
    
    result = await tool.safe_call(input_data, mock_session)
    assert result.is_success is True
    assert len(result.peaks) > 0
    # 兼容不同的单位写法 (unicode 或 字符串)
    assert "cm" in result.units and ("-1" in result.units or "⁻¹" in result.units)
    
    # 验证是否至少发现了一个峰
    print(f"\nDetected Peaks: {result.peaks}")
    assert any(p['wavenumber'] > 0 for p in result.peaks)

def test_nmr_processor_instantiation():
    """测试 NMR 解析器的实例化。"""
    tool = NMRProcessor()
    assert tool.tool_name == 'nmr_processor'
    assert tool.is_read() is True
