"""chem-kb：SQLite 图谱索引与来源知识稿读取。

``store.py`` 用实体关键词查找直接关联的来源，``content.py`` 按来源
组合 ``cards.jsonl`` 中的同语言段落；``plugin.py`` 将完整抽取整理稿
注册进 ``agent_hub`` 的图书馆层。图谱负责索引，知识稿负责正文，在线
检索不依赖向量服务。运行时不回写本库，维护通过 knowledge CLI 完成。
"""
