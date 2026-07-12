from pi_wiki_agent import WikiIndexer
# 试一下
indexer = WikiIndexer(r"D:\project\wiki-demo-taskman")
entries = indexer.full_rebuild()
print(f"索引了 {len(entries)} 条")
