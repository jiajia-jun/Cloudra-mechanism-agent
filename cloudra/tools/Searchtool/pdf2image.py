import os
from typing import Any

try:
    import fitz  # PyMuPDF
    _PYMUPDF_AVAILABLE = True
except Exception:
    fitz = None
    _PYMUPDF_AVAILABLE = False

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "将 PDF 文件逐页转换为高质量图片（基于 PyMuPDF），保存到指定输出目录。"
    "适用：pdf2md 转换失败或返回空内容时的兜底方案——转图后再用 image_reader 看图分析。"
    "不适用：文本型 PDF 的直接提取（首选 pdf2md）；"
    "每个 PDF 必须分配独立的新输出目录，避免 PNG 碎片文件污染共享目录。"
)


class pdf2image_input_schema(input_schema):
    pdf_path: str = Field(description="待转换的 PDF 文件的绝对路径")
    output_dir: str = Field(description="生成的图片输出目录。请务必为每个 PDF 文件分配一个专属且独立的新目录（例如临时目录下的 pdf_name_images），切勿将其直接输出在根目录或共享目录，以免大量 PNG 碎片文件造成环境污染。")


class pdf2image_output_schema(output_schema):
    is_success: bool = Field(description="是否转换成功")
    image_paths: list[str] = Field(default_factory=list, description="生成的图片绝对路径列表")
    message: str = Field(default="", description="转换过程的输出或错误信息")


class pdf2image(Tool):
    tool_id: str = 't-32'
    tool_name: str = 'pdf2image'
    tool_description: str = description
    input_schema: Any = pdf2image_input_schema
    output_schema: Any = pdf2image_output_schema

    def is_script(self) -> bool:
        return True

    async def tool_call(self, user_input: pdf2image_input_schema, session: Session) -> pdf2image_output_schema:
        if not _PYMUPDF_AVAILABLE:
            return pdf2image_output_schema(
                is_success=False,
                image_paths=[],
                message="环境未安装 PyMuPDF 库。请执行: pip install 'cloudra[pdf]'"
            )

        pdf_path = user_input.pdf_path
        output_dir = user_input.output_dir

        if not os.path.exists(pdf_path):
            return pdf2image_output_schema(
                is_success=False,
                image_paths=[],
                message=f"错误：文件不存在于路径 {pdf_path}"
            )

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            return pdf2image_output_schema(
                is_success=False,
                image_paths=[],
                message=f"创建输出目录失败：{str(e)}"
            )

        image_paths = []

        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # 提高分辨率，通常设置 matrix 2x2 或 3x3 会有较好的 OCR/读取效果
                # 此处采用 2x2，兼顾清晰度和文件大小
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

                # 提取 PDF 文件名作为前缀
                base_name = os.path.splitext(os.path.basename(pdf_path))[0]
                img_path = os.path.join(output_dir, f"{base_name}_page_{page_num + 1}.png")

                pix.save(img_path)
                image_paths.append(os.path.abspath(img_path))

            doc.close()

            return pdf2image_output_schema(
                is_success=True,
                image_paths=image_paths,
                message=f"成功将 PDF 转换为 {len(image_paths)} 张图片。"
            )
        except Exception as e:
            return pdf2image_output_schema(
                is_success=False,
                image_paths=image_paths,
                message=f"转换失败：{str(e)}"
            )


def get_class():
    return pdf2image
