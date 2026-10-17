"""Graph keywords index complete source knowledge texts for AgentHub.

Only graph matches retrieve documents. The graph is an index, not an answer
channel; no vector service, content scan or synthetic entity answer fills gaps.
All IO runs in search(), offloaded by the runtime's search_library host.
"""

from __future__ import annotations

from cloudra.knowledge import content, store
from cloudra.persistence.paths import knowledge_graph_db_path
from cloudra.runtime_v2.knowledge import KnowledgeEntry, flatten_tags

PLUGIN_SPEC = "cloudra.knowledge.plugin:plugin"


def _ascii_dominant(query: str) -> bool:
    tokens = query.split()
    return bool(tokens) and sum(token.isascii() for token in tokens) / len(tokens) >= 0.7


class ChemKBPlugin:
    name = "chem-kb"

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeEntry]:
        if limit < 1:
            return []
        matches = store.search_sources(knowledge_graph_db_path(), query)
        if not matches:
            return []
        sources = content.load_sources()
        preferred = "en" if _ascii_dominant(query) else "zh"
        entries: list[KnowledgeEntry] = []
        for match in matches:
            rows = sources.get(match["source"], [])
            sections: dict[str, dict] = {}
            for row in sorted(rows, key=lambda row: (
                row.get("lang", "zh") != preferred,
                row.get("lang", "zh") != "zh",
            )):
                sections.setdefault(row["card_id"], row)
            ordered = sorted(sections.values(), key=lambda row: int(row["card_id"].rsplit(":", 1)[1]))
            if not ordered:
                continue
            first = ordered[0]
            body = "\n\n".join(f"## {row['heading']}\n\n{row['content']}" for row in ordered)
            if first.get("file"):
                body = f"Knowledge file: 知识卡片/{first['file']}\n\n{body}"
            tags = list(dict.fromkeys(tag for row in ordered for tag in flatten_tags(row.get("tags"))))
            entries.append(KnowledgeEntry(
                title=first.get("fm_title") or first.get("topic") or first["heading"],
                content=body,
                source=match["source"],
                score=match["score"],
                tags=tags,
            ))
            if len(entries) >= limit:
                break
        return entries


plugin = ChemKBPlugin()
