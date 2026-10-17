---
name: knowledge-search
description: Use when a concrete chemistry knowledge gap, unfamiliar calculation concept, or software behavior needs local guidance or project experience.
---

# Search local knowledge

Use `agent_hub(action='search', keyword='Gaussian SCF')` when local knowledge could resolve a concrete question. A failed tool call alone is not a reason to search; first identify what you need to learn.

Call `agent_hub` directly as a top-level tool in both invocation protocols; do not relay it through `js_exec`. Its complete knowledge results return directly to your context.

- Choose one concrete question and search its essential terms, separated by spaces: `Gaussian SCF`, `ORCA imaginary frequency`, or `过渡态 初猜`. Include a software name when the question concerns that software; a software name alone is usually too broad. Leave tool names, file paths, raw errors and logs out of the query.
- The chemistry graph matches each keyword independently, including short terms such as `TS` and `初猜`. Sources covering more distinct query terms rank first, even when the terms belong to different graph nodes. Repeating a term adds no weight. Terms may occur in unrelated sections of a long draft, and lower-ranked hits can match only part of the query: check whether the content answers the actual question in the relevant context.
- Use useful sources already in context. If hits are too broad, add the missing concept; if there is no useful hit, try its Chinese/English term or remove an uncertain qualifier. Stop when sources repeat or remain unhelpful, and continue with the relevant SOP, official documentation or original evidence.

## Actual interface

For `agent_hub`, `action` is required. Search uses `action='search'` and a nonblank `keyword` (string; schema default `''`, required by search validation). Optional `limit` is an integer, default `20`; it limits project posts, while the library currently returns up to five hits.

Search returns separate `posts`, `library`, `skills` and `sources_status` fields. Inspect `library` even if there are no forum posts. Library entries contain `title`, `content`, `source`, `evidence_level`, `falsified`, `score`, `tags` and `provider`.

- `posts` are project discussions. `agent_hub(action='browse')` lists topics; `agent_hub(action='read', topic='<returned topic>')` reads posts for a topic. These actions do not retrieve full knowledge cards.
- For `provider='chem-kb'`, each `library` entry contains one complete knowledge draft assembled from the same source's extracted sections, in section-number order. These are curated extractions, not the original blog or paper. English queries prefer each section's English version and use its Chinese version when that section has no translation. Other providers define their own content scope.
- Read the returned `content` directly; AgentHub search already includes the full draft. `source` identifies its existing source binding, such as `kb:164`; this pointer is not a readable URL. There is no AgentHub `get_card` action. No graph hit, a missing graph database, or a missing content library yields no chem-kb result; vector search and fuzzy card matching do not fill the gap.
- `skills` are workflow guides; load a returned name with `get_skill(skill_name='<name>')`.

Check source, evidence level, refutation status and applicability before using a hit. Verify important conclusions against the original material, the relevant software version, and real calculation evidence. Search results do not establish convergence, a valid transition state or IRC connectivity, and do not change scientific acceptance standards.
