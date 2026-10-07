import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_existing_tool_path

description = (
    "Chemical structure image recognition (OCSR): convert printed or hand-drawn structure figures (PNG/JPG screenshots, etc.) to SMILES using the DECIMER deep-learning model. "
    "Use for: recovering a molecule from a paper screenshot or a sketch, then feeding SMILES to smiles_to_mol or molecule_drawer. "
    "Do not use for: merely viewing an image (use read) or drawing from an existing SMILES (use molecule_drawer)."
)


class ImageToSmiles_input_schema(input_schema):
    image_path: str = Field(
        description="Absolute or relative path of the chemical-structure image. Common formats such as PNG, JPG, JPEG, TIFF."
    )


class ImageToSmiles_output_schema(output_schema):
    is_success: bool = Field(description="Whether recognition succeeded")
    smiles: str = Field(default="", description="Recognized SMILES string. Empty on failure.")
    message: str = Field(default="", description="Status or error message")


class ImageToSmiles(Tool):
    tool_id: str = 't-10'
    tool_name: str = 'image_to_smiles'
    tool_description: str = description
    input_schema: Any = ImageToSmiles_input_schema
    output_schema: Any = ImageToSmiles_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: ImageToSmiles_input_schema, session: Session) -> ImageToSmiles_output_schema:
        try:
            path = resolve_existing_tool_path(self, user_input.image_path)
        except FileNotFoundError as exc:
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=str(exc),
            )

        # DECIMER 的 import 即在进程内加载 TensorFlow SavedModel，predict 是同步推理，
        # 两者都是分钟级 CPU 工作——必须离开事件循环线程，否则整个 API 饿死。
        predict_func, import_error_msg = await asyncio.to_thread(_load_predict_func)
        if predict_func is None:
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=(
                    "DECIMER is not installed. Install it with:\n"
                    "  pip install decimer\n"
                    "or:\n"
                    "  pip install git+https://github.com/Kohulan/DECIMER-Image_Transformer.git\n"
                    f"Original error: {import_error_msg}"
                )
            )

        try:
            smiles = await asyncio.to_thread(predict_func, path)
            if not isinstance(smiles, str):
                return ImageToSmiles_output_schema(
                    is_success=False,
                    smiles="",
                    message="DECIMER returned a non-text result; cannot recognize a chemical structure.",
                )
            smiles = smiles.strip()
            if not smiles:
                return ImageToSmiles_output_schema(
                    is_success=False,
                    smiles="",
                    message="DECIMER returned an empty result; no chemical structure was recognized from the image.",
                )
            # 识别结果零校验是静默错值的来源：必须 RDKit 校验（非法 SMILES 即失败，
            # 不得把 DECIMER 的胡话当成功结果回给 agent）。
            try:
                from rdkit import Chem
            except Exception as exc:
                return ImageToSmiles_output_schema(
                    is_success=False,
                    smiles="",
                    message=(
                        f"Cannot validate the recognized SMILES without RDKit: {exc}. "
                        "Install it with: pip install 'cloudra[chem]'"
                    ),
                )
            if Chem.MolFromSmiles(smiles) is None:
                return ImageToSmiles_output_schema(
                    is_success=False,
                    smiles="",
                    message=f"DECIMER output is not a valid SMILES string: {smiles!r} — refusing to report it as a structure.",
                )
            return ImageToSmiles_output_schema(
                is_success=True,
                smiles=smiles,
                message="Chemical structure recognized successfully."
            )
        except Exception as e:
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=f"Recognition raised an exception: {str(e)}"
            )


def _load_predict_func():
    """加载 DECIMER 的 predict_SMILES（支持 GitHub 版大写与 PyPI 版小写两种包名）。

    抽成函数便于测试注入假 DECIMER（识别结果校验单元不依赖真实模型）。
    """
    import_error_msg = ""
    for module_name, func_name in [("DECIMER", "predict_SMILES"), ("decimer", "predict_SMILES")]:
        try:
            mod = __import__(module_name, fromlist=[func_name])
            return getattr(mod, func_name), import_error_msg
        except ImportError as e:
            import_error_msg = str(e)
            continue
        except AttributeError as e:
            import_error_msg = str(e)
            continue
    return None, import_error_msg
