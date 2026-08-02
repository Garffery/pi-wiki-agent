# sync.yaml 编译输出

## 输入 YAML

```yaml
name: sync
description: 分析 VCS 提交并更新 wiki 页面
concurrency: 8

phases:
  - title: Analyze
    steps:
      - agent: diff-analyzer
        label: diff analysis
        prompt: |
          ## 提交信息
          ${commit_message}

          ## 变更文件
          ${join(changed_files, "- ${item}")}

          ## 受影响的 Wiki 章节
          ${affected_sections}

          ## Diff 文件目录
          ${diffs_dir}

          请逐一阅读 diff 目录下的文件，分析每个代码变更对 wiki 文档的影响。
          输出要求：
          - 每个变更文件单独一段分析
          - 说明：变更了什么 → 影响哪个 wiki 页面 → 大致需要如何更新
          - 如果某个文件不影响 wiki，标记为 "no wiki impact"

  - title: Plan
    steps:
      - agent: wiki-planner
        label: wiki planning
        prompt: |
          基于以下分析，为每个需要更新 wiki 的文件生成具体的操作指令：

          ${previous}

          要求：
          1. 对每个有实际 wiki 影响的变更文件，生成一条任务
          2. 同一 wiki 页面的多个文件修改，合并为一条任务
          3. 调用 structured_output 工具返回结果
        output_schema:
          file_tasks:
            - file: str
              wiki_page: str
              section: str?
              action: {enum: [create, update, delete]}
              instructions: str
          no_change_files: [str]

  - title: Write
    mode: dag
    for_each: ${outputs.Plan.file_tasks}
    steps:
      - agent: wiki-writer
        label: write-${item.wiki_page}
        prompt: |
          ## 任务
          任务 ID: ${item.id}
          源文件: ${item.file}
          目标 Wiki 页面: ${item.wiki_page}
          目标章节: ${item.section}
          操作类型: ${item.action}
          修改指令: ${item.instructions}

          ## 项目上下文
          项目路径: ${project_path}

          请根据上述指令修改对应的 wiki 页面。完成后简要说明做了什么修改。

```

## 生成的 Python 脚本

```python
meta = {'name': 'sync', 'description': '分析 VCS 提交并更新 wiki 页面', 'phases': [{'title': 'Analyze'}, {'title': 'Plan'}, {'title': 'Write'}]}
_outputs = {}
_prev = None
checkpoint.save('_meta', {'workflow': 'sync'})
phase('Analyze')
_p0_prev = checkpoint.load('Analyze') or {}
if _p0_prev.get('value') is not None:
    log('[checkpoint] Phase Analyze CHECKPOINT HIT')
    _s_result = _p0_prev['value']
else:
    _s1 = await agent(f'## 提交信息\n{args['commit_message']}\n\n## 变更文件\n{chr(10).join((f'- {f}' for f in args['changed_files']))}\n\n## 受影响的 Wiki 章节\n{args['affected_sections']}\n\n## Diff 文件目录\n{args['diffs_dir']}\n\n请逐一阅读 diff 目录下的文件，分析每个代码变更对 wiki 文档的影响。\n输出要求：\n- 每个变更文件单独一段分析\n- 说明：变更了什么 → 影响哪个 wiki 页面 → 大致需要如何更新\n- 如果某个文件不影响 wiki，标记为 "no wiki impact"\n', {'label': 'diff analysis', 'agent': 'diff-analyzer'})
    _r = _s1
    _s_result = _s1
    checkpoint.save('Analyze', {'value': _s_result, 'session_path': agent_session_path()})
_p0_results = _s_result
_outputs['Analyze'] = _p0_results
log('[DEBUG phase=Analyze] result_type=' + str(type(_p0_results).__name__) + ' len=' + str(len(str(_p0_results))))
phase('Plan')
_p1_prev = checkpoint.load('Plan') or {}
if _p1_prev.get('value') is not None:
    log('[checkpoint] Phase Plan CHECKPOINT HIT')
    _s_result = _p1_prev['value']
else:
    _s2 = await agent(f'基于以下分析，为每个需要更新 wiki 的文件生成具体的操作指令：\n\n{_p0_results}\n\n要求：\n1. 对每个有实际 wiki 影响的变更文件，生成一条任务\n2. 同一 wiki 页面的多个文件修改，合并为一条任务\n3. 调用 structured_output 工具返回结果\n', {'label': 'wiki planning', 'agent': 'wiki-planner', 'schema': '{"type": "object", "properties": {"file_tasks": {"type": "array", "items": {"type": "object", "properties": {"file": {"type": "string"}, "wiki_page": {"type": "string"}, "section": {"type": "string"}, "action": {"type": "string", "enum": ["create", "update", "delete"]}, "instructions": {"type": "string"}}, "required": ["file", "wiki_page", "section", "action", "instructions"]}}, "no_change_files": {"type": "array", "items": {"type": "string"}}}, "required": ["file_tasks", "no_change_files"]}'})
    _r = _s2
    _s_result = _s2
    checkpoint.save('Plan', {'value': _s_result, 'session_path': agent_session_path()})
_p1_results = _s_result
_outputs['Plan'] = _p1_results
log('[DEBUG phase=Plan] result_type=' + str(type(_p1_results).__name__) + ' len=' + str(len(str(_p1_results))))
phase('Write')
_p2_prev_tasks = (checkpoint.load('Write') or {}).get('value', {})
_p2_items = (_outputs.get('Plan') or {}).get('file_tasks') if isinstance(_outputs.get('Plan'), dict) and isinstance((_outputs.get('Plan') or {}).get('file_tasks'), list) else []
if _p2_items:
    _p2_dag_tasks = []
    for idx, it in enumerate(_p2_items):
        tid = it.get('id', f'task-{idx}')
        pe = _p2_prev_tasks.get(tid) or {}
        if pe.get('value') is not None:
            _p2_dag_tasks.append({'id': tid, 'fn': lambda v=pe['value']: v, 'depends_on': it.get('depends_on', [])})
        elif pe.get('session_path'):
            _p2_dag_tasks.append({'id': tid, 'fn': lambda it2=it, sp=pe['session_path']: agent(f'## 任务\n任务 ID: {it2.get('id')}\n源文件: {it2.get('file')}\n目标 Wiki 页面: {it2.get('wiki_page')}\n目标章节: {it2.get('section')}\n操作类型: {it2.get('action')}\n修改指令: {it2.get('instructions')}\n\n## 项目上下文\n项目路径: {args['project_path']}\n\n请根据上述指令修改对应的 wiki 页面。完成后简要说明做了什么修改。\n', {'label': f'write-{it2.get('wiki_page')}', 'agent': 'wiki-writer', 'resume_from': sp}), 'depends_on': it.get('depends_on', [])})
        else:
            _p2_dag_tasks.append({'id': tid, 'fn': lambda it2=it: agent(f'## 任务\n任务 ID: {it2.get('id')}\n源文件: {it2.get('file')}\n目标 Wiki 页面: {it2.get('wiki_page')}\n目标章节: {it2.get('section')}\n操作类型: {it2.get('action')}\n修改指令: {it2.get('instructions')}\n\n## 项目上下文\n项目路径: {args['project_path']}\n\n请根据上述指令修改对应的 wiki 页面。完成后简要说明做了什么修改。\n', {'label': f'write-{it2.get('wiki_page')}', 'agent': 'wiki-writer'}), 'depends_on': it.get('depends_on', [])})
    _p2_seed = {tid: v['value'] for tid, v in _p2_prev_tasks.items() if v.get('value') is not None}
    _p2_results_dict = await dag(_p2_dag_tasks, seed=_p2_seed)
    _p2_results = [_p2_results_dict.get(it.get('id', f'task-{idx}')) for idx, it in enumerate(_p2_items)]
    _wr = {}
    for idx, it in enumerate(_p2_items):
        tid = it.get('id', f'task-{idx}')
        r = _p2_results_dict.get(tid)
        cs = agent_session_path()
        old_s = _p2_prev_tasks.get(tid, {}).get('session_path')
        _wr[tid] = {'value': r, 'session_path': cs if r is not None else old_s}
    checkpoint.save('Write', {'value': _wr, 'session_path': None})
else:
    _p2_results = []
_outputs['Write'] = _p2_results
log('[DEBUG phase=Write] result_type=' + str(type(_p2_results).__name__) + ' len=' + str(len(str(_p2_results))))
if not args.get('keep_checkpoint'):
    checkpoint.clear()
return dict(_outputs)
```
