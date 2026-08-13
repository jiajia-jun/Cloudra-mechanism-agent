import asyncio
from pathlib import Path
from typing import Any

try:
    import fitz
    _PYMUPDF_AVAILABLE = True
except Exception:
    fitz = None
    _PYMUPDF_AVAILABLE = False

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

description = (
    "Convert PDF, Word, Excel, PPT, and other binary documents to Markdown (PyMuPDF), "
    "extracting text and images and returning the Markdown path plus extracted image list. "
    "Use for: reading local papers, reports, or slides — convert to Markdown first, then summarize, extract, or Q&A. "
    "Do not use for: failed conversion or scanned PDFs with no text layer (use pdf2image then image_reader); "
    "online PDFs must first be downloaded with web_fetcher download_path."
)


class pdf2md_input_schema(input_schema):
    input_path: str = Field(description="Absolute path of the file to convert")
    output_path: str = Field(description="Output directory for the converted Markdown file")
    timeout: int = Field(default=300, description="Conversion timeout in seconds")


class pdf2md_output_schema(output_schema):
    is_finished: bool = Field(description="Whether conversion succeeded")
    md_path: str = Field(description="Path of the generated Markdown file; empty string on failure")
    extracted_images: list[str] = Field(default_factory=list, description="Absolute paths of images extracted from the PDF")
    content: str = Field(default="", description="Conversion output or error message")


class pdf2md(Tool):
    tool_id: str = 't-3'
    tool_name: str = 'pdf2md'
    tool_description: str = description
    input_schema: Any = pdf2md_input_schema
    output_schema: Any = pdf2md_output_schema

    def is_script(self) -> bool:
        return True

    async def tool_call(self, user_input: pdf2md_input_schema, session: Session) -> pdf2md_output_schema:
        if not _PYMUPDF_AVAILABLE:
            return pdf2md_output_schema(
                is_finished=False,
                md_path='',
                content="环境未安装 PyMuPDF 库。请执行: pip install 'cloudra[pdf]'"
            )

        input_path = user_input.input_path
        target_path = user_input.output_path
        timeout = user_input.timeout

        try:
            return await asyncio.wait_for(
                self._convert(input_path, target_path),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return pdf2md_output_schema(
                is_finished=False,
                md_path='',
                content='PDF 转换超时！'
            )
        except Exception as e:
            return pdf2md_output_schema(
                is_finished=False,
                md_path='',
                content=f'PDF 转换失败: {e}'
            )

    async def _convert(self, input_path: str, target_path: str) -> pdf2md_output_schema:
        """使用 PyMuPDF 将 PDF 转换为 Markdown。"""
        input_path_obj = Path(input_path)
        target_path_obj = Path(target_path)
        stem = input_path_obj.stem

        output_dir = target_path_obj / stem
        images_dir = output_dir / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        md_file_path = output_dir / f"{stem}.md"

        # 在后台线程运行 CPU 密集型 PDF 解析
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._convert_sync,
            input_path,
            output_dir,
            images_dir,
            md_file_path,
        )

    def _convert_sync(
        self,
        input_path: str,
        output_dir: Path,
        images_dir: Path,
        md_file_path: Path,
    ) -> pdf2md_output_schema:
        doc = fitz.open(input_path)
        md_lines: list[str] = []
        extracted_images: list[str] = []
        image_counter = 0
        seen_image_xrefs: set[int] = set()

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            md_lines.append(f"\n## 第 {page_num + 1} 页\n")

            # 提取文本块
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))  # 按垂直位置、再按水平位置排序

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block[:7]
                if block_type != 0 or not text.strip():
                    continue

                # 简单启发式：字体较大或粗体视为标题
                # 这里仅做段落处理，保留换行
                paragraph = text.strip().replace('\n', ' ')
                if paragraph:
                    md_lines.append(f"{paragraph}\n")

            # 提取图片
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list, start=1):
                xref = img[0]
                if xref in seen_image_xrefs:
                    continue
                seen_image_xrefs.add(xref)

                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    image_counter += 1
                    image_filename = f"image_{image_counter:04d}.{image_ext}"
                    image_path = images_dir / image_filename
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    rel_path = f"images/{image_filename}"
                    md_lines.append(f"\n![image_{image_counter}]({rel_path})\n")
                    extracted_images.append(str(image_path.absolute()))
                except Exception as e:
                    md_lines.append(f"\n<!-- 图片提取失败: {e} -->\n")

        doc.close()

        md_content = "\n".join(md_lines)
        md_file_path.write_text(md_content, encoding="utf-8")

        return pdf2md_output_schema(
            is_finished=True,
            md_path=str(md_file_path.absolute()),
            extracted_images=extracted_images,
            content=f"转换完成，共处理 {len(md_lines)} 行文本，提取 {len(extracted_images)} 张图片。",
        )


def get_class():
    return pdf2md
