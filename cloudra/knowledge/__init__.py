"""Knowledge-graph subsystem (chem-kb): SQLite store + hybrid library provider.

与 ``runtime_v2/knowledge.py``（图书馆协议：KnowledgeEntry、search_library
合并排序）的关系：本子包是协议的**数据侧实现**——``store.py`` 拥有并维护
chem_kg.db（实体/行级关系，源自 知识卡片 洁净版抽取的 KG CSV），
``plugin.py`` 把图谱检索与向量微服务缝合成单一混合 provider 注册进
``agent_hub`` 的图书馆层。核心不写本库（无自演化），维护入口只有
``cloudra knowledge import`` CLI。
"""
