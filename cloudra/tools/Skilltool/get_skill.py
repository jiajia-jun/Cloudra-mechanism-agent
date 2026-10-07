import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.skill_class import skill_loader
from cloudra.base.tools_class import Tool, input_schema, output_schema


class GetSkill_input_schema(input_schema):
    skill_name: str = Field(
        description="Name of the skill to load."
    )
    reference: str = Field(
        default="",
        description="After reading a skill, pass this to load a reference mentioned in the parent skill (the ref name)."
    )


class GetSkill_output_schema(output_schema):
    is_success: bool = Field(
        description="Whether the skill content was loaded."
    )
    content: str = Field(
        description="Loaded skill content."
    )
    result: str = Field(
        description="Tool result."
    )


class GetSkill(Tool):

    tool_id: str = 't-25'
    tool_name: str = 'get_skill'
    # NOTE: description 保持惰性，不内嵌 skill 清单——system prompt 的
    # "Current skill manifest" 区块已对所有角色注入同一份清单，
    # 这里再列一遍会让每个请求带上双份。
    tool_description: str = (
        "Load the full SOP for a named skill. A skill carries domain knowledge and workflow: "
        "before starting any task that has a matching skill (e.g. DFT, molecular dynamics, paper writing, literature search), "
        "you must call this tool to load that skill and follow its procedure, completion criteria, and caveats. "
        "See the \"Current skill manifest\" section of the system prompt for the available skill names "
        "and pass one as skill_name. "
        "When the skill mentions references, pass the ref name in reference to read the corresponding reference file."
    )
    input_schema: Any = GetSkill_input_schema
    output_schema: Any = GetSkill_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(
        self,
        user_input: GetSkill_input_schema,
        session: Session
    ) -> GetSkill_output_schema:
        return await asyncio.to_thread(self._load_skill, user_input)

    def _load_skill(self, user_input: GetSkill_input_schema) -> GetSkill_output_schema:
        import difflib

        loader = skill_loader()
        skill_name = (user_input.skill_name or "").strip()
        ref = (user_input.reference or "").strip()

        all_skills = loader.list_skills()
        skill_names = [s["name"] for s in all_skills]

        # 1. List catalog if empty or asking for list
        if not skill_name or skill_name.lower() in ("list", "help", "all"):
            skill_list_text = "\n".join(f"- **{s['name']}**: {s['description']}" for s in all_skills)
            return GetSkill_output_schema(
                is_success=True,
                content=f"# Available Skills Catalog\n\n{skill_list_text}\n\nCall `get_skill(skill_name='<name>')` to load a skill.",
                result=f"Listed {len(all_skills)} available skills.",
            )

        # 2. Check skill existence with fuzzy suggestion
        if skill_name not in skill_names:
            matches = difflib.get_close_matches(skill_name, skill_names, n=3, cutoff=0.35)
            suggestion = f" Did you mean '{matches[0]}'?" if matches else ""
            return GetSkill_output_schema(
                is_success=False,
                content="",
                result=f"Skill '{skill_name}' does not exist.{suggestion} Available skills: {skill_names}."
            )

        # 3. Collect available references for this skill
        available_refs = loader.list_references(skill_name)
        ref_guide = ""
        if available_refs:
            ref_list_str = "\n".join(f"- `{r}`" for r in available_refs)
            ref_guide = (
                f"\n\n--- Available Reference Guides in '{skill_name}' ---\n"
                f"You can load any of the following reference files via `get_skill(skill_name=\"{skill_name}\", reference=\"<filename>\")`:\n"
                f"{ref_list_str}\n"
            )

        # 4. Handle specific reference loading
        if ref:
            ref_content = loader.get_reference(skill_name, ref)
            if ref_content in ('Reference not found.', '该资料不存在。'):
                return GetSkill_output_schema(
                    is_success=False,
                    content=f"Reference '{ref}' not found in skill '{skill_name}'.\n\n{ref_guide}",
                    result=f"Reference '{ref}' not found in skill '{skill_name}'. Available references: {available_refs}.",
                )
            content = f"# Reference: {skill_name}/{ref}\n\n{ref_content}"
            result = f"Loaded reference '{ref}' from skill '{skill_name}'."
        else:
            content = loader.get_content(skill_name) + ref_guide
            result = f"Loaded skill '{skill_name}'."
            if available_refs:
                result += f" ({len(available_refs)} reference guides available)."

        return GetSkill_output_schema(
            is_success=True,
            content=content,
            result=result
        )
