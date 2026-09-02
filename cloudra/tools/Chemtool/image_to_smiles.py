import os
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

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
        path = user_input.image_path
        if not os.path.exists(path):
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=f"File does not exist: {path}"
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
                    "DECIMER is not installed. Install it with:\n"
                    "  pip install decimer\n"
                    "or:\n"
                    "  pip install git+https://github.com/Kohulan/DECIMER-Image_Transformer.git\n"
                    f"Original error: {import_error_msg}"
                )
            )

        try:
            smiles = predict_func(path)
            if not smiles or not isinstance(smiles, str):
                return ImageToSmiles_output_schema(
                    is_success=False,
                    smiles="",
                    message="DECIMER could not recognize a valid chemical structure from the image."
                )
            return ImageToSmiles_output_schema(
                is_success=True,
                smiles=smiles.strip(),
                message="Chemical structure recognized successfully."
            )
        except Exception as e:
            return ImageToSmiles_output_schema(
                is_success=False,
                smiles="",
                message=f"Recognition raised an exception: {str(e)}"
            )


def get_class():
    return ImageToSmiles
