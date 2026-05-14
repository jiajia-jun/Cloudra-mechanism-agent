from pydantic import Field
from typing import Any

from tools_class import Tool, input_schema, output_schema
from session_class import Session
import asyncio


description = (
    "使用 MinerU 将 PDF 等二进制文档转换为 Markdown 格式。"
    "适用于处理学术文献、Word、Excel 等非纯文本文件。"
)


class pdf2md_input_schema(input_schema):
    input_path: str = Field(description="待转换文件的绝对路径")
    output_path: str = Field(description="转换后 Markdown 文件的输出目录")
    timeout: int = Field(default=60, description="转换超时时间（秒）")


class pdf2md_output_schema(output_schema):
    is_finished: bool = Field(description="是否转换成功")
    md_path: str = Field(description="生成的 Markdown 文件路径，失败时为空字符串")
    extracted_images: list[str] = Field(default_factory=list, description="从 PDF 中提取出的图片绝对路径列表")
    content: str = Field(default="", description="转换过程的输出或错误信息")


class pdf2md(Tool):
    tool_id: str = 't-3'
    tool_name: str = 'pdf2md'
    tool_description: str = description
    input_schema: Any = pdf2md_input_schema
    output_schema: Any = pdf2md_output_schema

    def is_script(self) -> bool:
        return True

    async def tool_call(self, user_input: pdf2md_input_schema, session: Session) -> pdf2md_output_schema:
        input_path = user_input.input_path
        target_path = user_input.output_path
        command = f'mineru -p "{input_path}" -o "{target_path}" -b pipeline'
        timeout = user_input.timeout

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            return pdf2md_output_schema(
                is_finished=False,
                md_path='',
                content='命令执行超时！'
            )
        except Exception as e:
            return pdf2md_output_schema(
                is_finished=False,
                md_path='',
                content=f'命令执行失败:{e}'
            )

        if stderr and b"error" in stderr.lower():
            return pdf2md_output_schema(
                is_finished=False,
                md_path='',
                content=stderr.decode('utf-8')
            )

        # 扫描提取出的图片
        # MinerU 通常在 target_path/{filename}/images 目录下生成图片
        extracted_images = []
        try:
            import os
            from pathlib import Path
            
            # 获取 PDF 文件名（不含后缀）
            pdf_stem = Path(input_path).stem
            # 搜索 MinerU 的输出子目录
            potential_img_dir = Path(target_path) / pdf_stem / "images"
            
            if potential_img_dir.exists() and potential_img_dir.is_dir():
                for img_file in potential_img_dir.iterdir():
                    if img_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                        extracted_images.append(str(img_file.absolute()))
        except Exception as e:
            # 即使扫描图片失败，也不影响 MD 转换的结果返回
            print(f"扫描图片目录时发生异常: {e}")

        # 寻找生成的 markdown 文件路径
        md_file_path = ""
        pdf_stem = Path(input_path).stem
        potential_md = Path(target_path) / pdf_stem / f"{pdf_stem}.md"
        if potential_md.exists():
            md_file_path = str(potential_md.absolute())

        return pdf2md_output_schema(
            is_finished=True,
            md_path=md_file_path if md_file_path else target_path,
            extracted_images=extracted_images,
            content=stdout.decode('utf-8')
        )


def get_class():
    return pdf2md
