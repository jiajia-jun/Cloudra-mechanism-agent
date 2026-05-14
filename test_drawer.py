import asyncio
import os
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.append(str(Path(__file__).parent))

from tools.Chemtool.molecule_drawer import MoleculeDrawer, MoleculeDrawer_input_schema
from session_class import Session

from unittest.mock import patch

async def test_molecule_drawer():
    # 1. 准备 Mock Session
    session = Session(id="test_session", path="test_session.json")
    
    # 2. 准备工具实例
    drawer = MoleculeDrawer()
    
    # 3. 构造输入
    input_data = MoleculeDrawer_input_schema(
        smiles="C1=CC=CC=C1",
        output_path=str(Path(__file__).parent / "benzene_test.png"),
        width=300,
        height=300,
        add_atom_indices=True
    )

    # 4. 调用工具 (使用 patch 绕过安全检查)
    print("开始调用 tool_call...")
    with patch.object(MoleculeDrawer, 'ensure_safety', return_value=True):
        # 注意：由于 ensure_safety 是 async，我们需要确保 mock 返回的是一个可 await 的 True
        async def mock_approved(*args, **kwargs):
            return True
        
        with patch('tools.Chemtool.molecule_drawer.MoleculeDrawer.ensure_safety', new=mock_approved):
            result = await drawer.tool_call(input_data, session)
    
    # 5. 验证结果
    print(f"执行结果: {result.is_success}")
    print(f"返回消息: {result.message}")
    
    if os.path.exists(input_data.output_path):
        print(f"成功！文件已生成: {input_data.output_path}")
        # 清理测试文件
        # os.remove(input_data.output_path)
    else:
        print("失败：文件未生成。")

if __name__ == "__main__":
    asyncio.run(test_molecule_drawer())
