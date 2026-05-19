---
name: subagent-prompting
description: Guidelines for writing effective prompts for sub-agents (explorer, writer, researcher). Use when delegating tasks via SubAgentLauncher to ensure sub-agents work correctly, avoid hallucinations, and operate in the correct directories.
---

# Sub-agent Prompting Guidelines

When launching a sub-agent (a-1, a-2, a-3), follow these principles to avoid "hallucinations" (like sub-agents searching for skills when they should be writing) and ensure they operate in the correct location.

## 1. Always Use Absolute Paths
Sub-agents might not inherit your current working directory correctly if it's relative.
*   **Bad**: `Write a poem in poem.txt`
*   **Good**: `Write a poem in /home/yyy2333/Cloudra/program/agent4chem/poem.txt`
*   **CWD**: Your current working directory is provided in your system prompt. Use it to construct absolute paths.

## 2. Be Explicit About the Task
Do not give vague instructions. If you know exactly what needs to be written, provide it in the `query` or `reasoning_prompt`.
*   **Bad**: `Write a poem about chemistry.` (Sub-agent might try to use `get_skill` to find out what "chemistry" is).
*   **Good**: `Write the following poem to /path/to/file.txt: [Poem Content]. Use the text_writer tool directly. Do NOT use other tools like get_skill.`

## 3. Restrict Tool Usage
If the task is straightforward, explicitly tell the sub-agent which tools to use and which to avoid.
*   **Guidance**: "Directly use `text_writer` to save the content. Do not search for additional information unless explicitly requested."

## 4. Provide Pre-calculated Context
If you have data (e.g., search results, file contents), pass it in the `context` parameter of `SubAgentLauncher` or include it directly in the `query`. This prevents the sub-agent from re-doing your work.

## 5. Structured Task Description
Use a format like this for the `query`:
```text
Task: [Action]
Target Path: [Absolute Path]
Content: [Exact content or detailed requirements]
Constraints: [Tool restrictions, e.g., 'Do not use search tools']
```

## 6. Synchronous vs. Asynchronous
*   Use `is_wait=True` when you need the sub-agent's result to proceed with your own logic (e.g., "Write this file and then I will verify it").
*   Use `is_wait=False` for background tasks that don't block your current reasoning.
