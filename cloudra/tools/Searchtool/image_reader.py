import os
from typing import Any

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "视觉感知工具：读取本地图像文件（PNG/JPG/JPEG/WEBP）并将其载入 Agent 的视觉上下文，"
    "使 Agent 能“看到”图片内容并进行分析、描述或对比。"
    "适用：分析本地已有图片，如分子结构图、谱图截图、实验装置照片。"
    "不适用：PDF 页面（先用 pdf2md，失败再 pdf2image 转图后读本工具）、"
    "从化学结构图反推 SMILES（用 image_to_smiles）。"
)

class ImageReader_input_schema(input_schema):
    image_path: str = Field(description="待读取图像文件的绝对路径")
    description: str = Field(default="请分析这张图片的内容。", description="希望 Agent 关注的视觉重点说明")

class ImageReader_output_schema(output_schema):
    is_success: bool = Field(description="是否成功读取图片")
    image_path: str = Field(description="图片的绝对路径（供系统内部多模态引擎调用）")
    message: str = Field(default="", description="读取状态或错误信息")

class ImageReader(Tool):
    tool_id: str = 't-27'
    tool_name: str = 'image_reader'
    tool_description: str = description
    input_schema: Any = ImageReader_input_schema
    output_schema: Any = ImageReader_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: ImageReader_input_schema, session: Session) -> ImageReader_output_schema:
        path = user_input.image_path

        # 验证文件是否存在
        if not os.path.exists(path):
            return ImageReader_output_schema(
                is_success=False,
                image_path="",
                message=f"错误：文件不存在于路径 {path}"
            )

        # 验证是否为支持的图片格式
        ext = os.path.splitext(path)[1].lower()
        if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
            return ImageReader_output_schema(
                is_success=False,
                image_path="",
                message=f"错误：不支持的文件格式 {ext}。目前仅支持 PNG, JPG, JPEG, WEBP。"
            )

        # 返回路径。reAct.py 探测到 image_path 字段后，会自动触发多模态发送逻辑。
        return ImageReader_output_schema(
            is_success=True,
            image_path=path,
            message=f"已成功加载图片：{path}。{user_input.description}"
        )

def get_class():
    return ImageReader
