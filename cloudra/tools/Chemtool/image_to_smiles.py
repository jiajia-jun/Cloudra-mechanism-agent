import os
from pydantic import Field
from typing import Any
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session


description = (
    "化学结构图像识别工具 (OCSR)：基于 DECIMER 深度学习模型，"
    "将化学结构图（如 PNG/JPG 截图、手绘结构）转换为 SMILES 字符串。"
    "支持印刷体、手绘等多种风格的化学结构识别。"
)


class ImageToSmiles_input_schema(input_schema):
    image_path: str = Field(
        description="化学结构图像文件的绝对路径或相对路径。支持 PNG、JPG、JPEG、TIFF 等常见格式。"
    )


class ImageToSmiles_output_schema(output_schema):
    is_success: bool = Field(description="识别是否成功")
    smiles: str = Field(default="", description="识别出的 SMILES 字符串。失败时为空。")
    message: str = Field(default="", description="执行信息或错误提示")


class ImageToSmiles(Tool):
    tool_id: str = 't-10'
    tool_name: str = 'image_to_smiles'
    tool_description: str = description
    input_schema: Any = ImageToSmiles_input_schema
    output_schema: Any = ImageToSmiles_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: ImageToSmiles_input_schema, session: Session) -> ImageToSmiles_output_schema:
        path = user_input.image_path
        if not os.path.exists(path):
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=f"文件不存在: {path}"
            )

        # 尝试导入 DECIMER（支持 GitHub 版大写和 PyPI 版小写两种包名）
        predict_func = None
        import_error_msg = ""
        for module_name, func_name in [("DECIMER", "predict_SMILES"), ("decimer", "predict_SMILES")]:
            try:
                mod = __import__(module_name, fromlist=[func_name])
                predict_func = getattr(mod, func_name)
                break
            except ImportError as e:
                import_error_msg = str(e)
                continue
            except AttributeError as e:
                import_error_msg = str(e)
                continue

        if predict_func is None:
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=(
                    "环境未安装 DECIMER 库。请执行以下命令安装:\n"
                    "  pip install decimer\n"
                    "或:\n"
                    "  pip install git+https://github.com/Kohulan/DECIMER-Image_Transformer.git\n"
                    f"原始错误: {import_error_msg}"
                )
            )

        try:
            smiles = predict_func(path)
            if not smiles or not isinstance(smiles, str):
                return ImageToSmiles_output_schema(
                    is_success=False,
                    smiles="",
                    message="DECIMER 未能从图像中识别出有效的化学结构。"
                )
            return ImageToSmiles_output_schema(
                is_success=True,
                smiles=smiles.strip(),
                message="化学结构识别成功。"
            )
        except Exception as e:
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=f"识别过程发生异常: {str(e)}"
            )


def get_class():
    return ImageToSmiles
