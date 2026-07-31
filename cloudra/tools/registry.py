"""Explicit built-in tool manifest.

Keep this module dependency-free: :mod:`cloudra.agent` imports
``cloudra.tools`` while several tool implementations import ``cloudra.agent``.
The registry therefore stores import paths instead of importing tool classes at
module import time.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolRegistration:
    module: str
    class_name: str


TOOL_REGISTRY: tuple[ToolRegistration, ...] = (
    ToolRegistration("cloudra.tools.Bashtool.bashtools", "Bashtools"),
    ToolRegistration("cloudra.tools.Browsertool.headless_browser", "HeadlessBrowser"),
    ToolRegistration("cloudra.tools.Browsertool.web_fetcher", "WebFetcher"),
    ToolRegistration("cloudra.tools.Chemtool.format_converter", "FormatConverter"),
    ToolRegistration("cloudra.tools.Chemtool.gjf_writer", "GjfWriter"),
    ToolRegistration("cloudra.tools.Chemtool.image_to_smiles", "ImageToSmiles"),
    ToolRegistration("cloudra.tools.Chemtool.internal_coordinates", "InternalCoordinates"),
    ToolRegistration("cloudra.tools.Chemtool.ir_processor", "IRProcessor"),
    ToolRegistration("cloudra.tools.Chemtool.log_parser", "LogParser"),
    ToolRegistration("cloudra.tools.Chemtool.molecule_drawer", "MoleculeDrawer"),
    ToolRegistration("cloudra.tools.Chemtool.nmr_processor", "NMRProcessor"),
    ToolRegistration("cloudra.tools.Chemtool.smiles_to_mol", "SmilesToMol"),
    ToolRegistration("cloudra.tools.Chemtool.submit_compute_job", "SubmitComputeJob"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceWorkspaceList"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceWorkspaceRead"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceConfigGet"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceWorkspaceApplyPatch"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceConfigPatch"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceDocumentsList"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceDocumentsRead"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceDocumentsWrite"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceFilePick"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceCameraCapture"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceShareText"),
    ToolRegistration("cloudra.tools.DeviceTool.device_tools", "DeviceNotify"),
    ToolRegistration("cloudra.tools.Interactool.ask_user", "AskUser"),
    ToolRegistration("cloudra.tools.Interactool.email_reader", "EmailReader"),
    ToolRegistration("cloudra.tools.Interactool.email_sender", "EmailSender"),
    ToolRegistration("cloudra.tools.Managetool.agent_hub", "AgentHub"),
    ToolRegistration("cloudra.tools.Managetool.get_subagent_report", "GetSubAgentReport"),
    ToolRegistration("cloudra.tools.Managetool.schedule", "Schedule"),
    ToolRegistration("cloudra.tools.Managetool.subagent_launcher", "SubAgentLauncher"),
    ToolRegistration("cloudra.tools.Plantool.goal", "GoalSet"),
    ToolRegistration("cloudra.tools.Plantool.todo", "TodoWrite"),
    ToolRegistration("cloudra.tools.Searchtool.openalex_searcher", "OpenAlexSearcher"),
    ToolRegistration("cloudra.tools.Searchtool.image_reader", "ImageReader"),
    ToolRegistration("cloudra.tools.Searchtool.paper_searcher", "PaperSearcher"),
    ToolRegistration("cloudra.tools.Searchtool.pdf2image", "pdf2image"),
    ToolRegistration("cloudra.tools.Searchtool.pdf2md", "pdf2md"),
    ToolRegistration("cloudra.tools.Searchtool.text_reader", "TextReader"),
    ToolRegistration("cloudra.tools.Searchtool.web_search", "WebSearch"),
    ToolRegistration("cloudra.tools.Skilltool.get_skill", "GetSkill"),
    ToolRegistration("cloudra.tools.Stoptool.stop_tool", "StopTool"),
    ToolRegistration("cloudra.tools.Writetool.edit_file", "EditFile"),
    ToolRegistration("cloudra.tools.Writetool.text_writer", "TextWriter"),
    ToolRegistration("cloudra.tools.Writetool.update_memory", "UpdateMemory"),
)
