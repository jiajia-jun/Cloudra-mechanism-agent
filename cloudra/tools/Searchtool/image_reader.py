import os
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Vision tool: read a local image (PNG/JPG/JPEG/WEBP) into the Agent's visual context "
    "so the Agent can see the image and analyze, describe, or compare it. "
    "Use for: analyzing existing local images such as molecular structures, spectrum screenshots, or apparatus photos. "
    "Do not use for: PDF pages (try pdf2md first; if that fails, pdf2image then this tool) "
    "or recovering SMILES from a chemical structure drawing (use image_to_smiles)."
)

class ImageReader_input_schema(input_schema):
    image_path: str = Field(description="Absolute path of the image file to read")
    description: str = Field(default="Analyze the content of this image.", description="What the Agent should focus on in the image")

class ImageReader_output_schema(output_schema):
    is_success: bool = Field(description="Whether the image was read")
    image_path: str = Field(description="Absolute path of the image (for the internal multimodal engine)")
    message: str = Field(default="", description="Read status or error message")

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
                message=f"Error: file does not exist at path {path}"
            )

        # 验证是否为支持的图片格式
        ext = os.path.splitext(path)[1].lower()
        if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
            return ImageReader_output_schema(
                is_success=False,
                image_path="",
                message=f"Error: unsupported file format {ext}. Only PNG, JPG, JPEG, WEBP are supported."
            )

        # 返回路径。runtime_v2 的 AgentRunner 探测到 tool result data 里的
        # image_path 字段后，在 visual 模式下自动把图片以 image_url part 回注
        # 进 LLM history（模型无视觉能力时降级为文本回落）。
        return ImageReader_output_schema(
            is_success=True,
            image_path=path,
            message=f"Image loaded: {path}. {user_input.description}"
        )

def get_class():
    return ImageReader
