import os
from typing import Any

try:
    import fitz  # PyMuPDF
    _PYMUPDF_AVAILABLE = True
except Exception:
    fitz = None
    _PYMUPDF_AVAILABLE = False

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Convert a PDF to high-quality per-page images (PyMuPDF) and save them to a given output directory. "
    "Use for: fallback when pdf2md fails or returns empty — convert to images, then analyze with image_reader. "
    "Do not use for: extracting text from a text-layer PDF (prefer pdf2md); "
    "each PDF must get its own new output directory so PNG fragments do not pollute a shared folder."
)


class pdf2image_input_schema(input_schema):
    pdf_path: str = Field(description="Absolute path of the PDF to convert")
    output_dir: str = Field(description="Output directory for generated images. Assign a dedicated new directory per PDF (e.g. a temp dir named pdf_name_images); do not write into the workspace root or a shared folder, or PNG fragments will pollute the environment.")


class pdf2image_output_schema(output_schema):
    is_success: bool = Field(description="Whether conversion succeeded")
    image_paths: list[str] = Field(default_factory=list, description="Absolute paths of generated images")
    message: str = Field(default="", description="Conversion output or error message")


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
                message="PyMuPDF is not installed. Install it with: pip install 'cloudra[pdf]', then retry."
            )

        pdf_path = user_input.pdf_path
        output_dir = user_input.output_dir

        if not os.path.exists(pdf_path):
            return pdf2image_output_schema(
                is_success=False,
                image_paths=[],
                message=f"Error: file does not exist at path {pdf_path}. Check the path, then retry."
            )

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            return pdf2image_output_schema(
                is_success=False,
                image_paths=[],
                message=f"Failed to create the output directory: {str(e)}"
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
                message=f"Converted the PDF to {len(image_paths)} images."
            )
        except Exception as e:
            return pdf2image_output_schema(
                is_success=False,
                image_paths=image_paths,
                message=f"Conversion failed: {str(e)}. Check that {pdf_path} is a valid, readable PDF."
            )


def get_class():
    return pdf2image
