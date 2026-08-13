---
name: subagent-prompting
description: Provide best practices and templates for writing effective prompts for sub-agents (e.g., explorer, writer, researcher). Use when delegating tasks via SubAgentLauncher to ensure sub-agents operate correctly, avoid hallucinations, manage context, and handle errors robustly.
---

# 1. Local toolchain mapping (Toolchain Mapping)
In a complex agent architecture (ReAct or multi-agent collaboration), when the main agent dispatches work to a sub-agent via tools such as `SubAgentLauncher`, map state and tool permissions physically:
- **Strip unnecessary dependencies**: a sub-agent does not necessarily inherit all of the parent’s tools and state. In the prompt, if the sub-agent only needs compute, explicitly forbid web search and other unrelated tools.
- **Use absolute paths**: a sub-agent’s working directory (CWD) is independent. For any file the sub-agent must read or modify, put the **absolute path** in the instructions (e.g. `/home/yyy2333/.../file.txt`); avoid relative paths or vague references.

# 2. Constraints and anti-hallucination guardrails (Constraints & Guardrails)
Without constraints, a large model will readily “pretend the task is done” and invent results.
1. **Avoid vague reference**: do not write “process the result above”; restating the core entities and goal by name.
2. **Trust but verify**: do not take a sub-agent’s claim that “the file was modified” or “the data was found” at face value. Require in its instructions that after a critical step it call the matching read tool (e.g. `log_parser` or a file-slice read) and present the result in the reply as proof.
3. **Stop log floods**: in the prompt, forbid the sub-agent from dumping extremely long files (e.g. `OUTCAR` or logs over 1000 lines); require a specific tool or script to parse the critical parts.

# 3. Knowledge base: S.C.A.R.F. standard template (Scientific Knowledge Base)
When sending instructions to a sub-agent, wrap complex-task prompts in the following blocks (S.C.A.R.F.); simple tasks may be trimmed — do not force the full template.

- **(S) System Role / role boundary**: define the professional role and behavioral red lines.
  *(Example: You are an analytical agent that only handles crystal symmetry; avoid impressionistic inference.)*
- **(C) Context / established facts**: pass already-confirmed facts so it need not re-verify them.
  *(Example: Total electron count for this system is confirmed as 120; the target file is at /path/to/log.out.)*
- **(A) Actionable Goal / precise objective**: an atomic task that must not wander.
  *(Example: Extract the final SCF energy and convert it to kcal/mol.)*
- **(R) Restrictions / limits and fallback**: circuit-breaker and error fallback when things go wrong.
  *(Example: If extraction is empty, return `[Result: Empty]`; do not invent numbers.)*
- **(F) Format / output contract**: agreed JSON or tagged output format.

# 4. Agent workflow: parallel and async dispatch (Workflow State Machine)
When deciding whether a sub-agent should run synchronously (Wait) or asynchronously in the background (Async), follow this decision tree:

**Step 1: Judge task dependence**
- If it is a hard prerequisite in a linear workflow (e.g. checking that the environment is installed and configured), set it to **synchronous blocking**.
- If it is large-scale data processing (e.g. independently scoring 10 different docking poses) or a broad literature search, set it to **async background**.

**Step 2: Resolve async conflicts**
- All parallel async sub-agents must write results to a designated path with an **independent UUID or process-id suffix** (e.g. `result_1234.txt`), so concurrent agents do not overwrite one shared result file and dirty-write.

# 5. Diagnostics and circuit breakers (Circuit Breakers)
The most dangerous sub-agent failure mode is a tool-call infinite loop. When dispatching, you may implant “step-back reasoning” in the prompt:

1. **Hard retry threshold**: state in the instructions: “If the same tool produces the same Error twice in a row, abandon that tool unconditionally.”
2. **Circuit-break report**: after abandoning, the sub-agent must `send_message` the main agent, attaching:
   - The original error (Stderr).
   - The last method attempted.
   - The specific step that is blocking the task.
