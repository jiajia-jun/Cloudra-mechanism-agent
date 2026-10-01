# 完整性与溯源

- raw_inventory.json/csv 与 catalog.sqlite3/files：本次整理前原始归档全部文件的路径、字节数、SHA、类别、题目、epoch。
- final_snapshot/：6776 个固定文件的原远端 manifest、大小写映射、全量 SHA/五库核验、平台停费凭证。
- ORGANIZATION_VERIFICATION.json：整理后重新核验原始文件、派生文件、链接、JSONL 记录数及全部原库。
- organized_manifest.json：本次新建文档、导出和目录索引的 SHA；验证器自身不包含其动态结果文件。

原始同名文件在不同 epoch 的 SHA 可不同，属历史变化，不能当成内容冲突后删掉。数据库结构完整性与化学验收是两个不同条件；可读并不表示某个鞍点、端点或能垒科学有效。
