meta = {
    'name': 'wiki_sync',
    'description': 'Analyze VCS commit and update wiki pages with parallel writer agents',
    'phases': [
        {'title': 'Analyze', 'detail': 'Analyze code diff impact on wiki sections'},
        {'title': 'Plan', 'detail': 'Create per-file wiki update tasks'},
        {'title': 'Write', 'detail': 'Execute wiki updates in parallel'},
    ],
}

# ——— Phase 1: 分析代码变更对 wiki 的影响 ———
phase('Analyze')
analysis = await agent(f'''
## 提交信息
{args['commit_message']}

## 变更文件
{chr(10).join('- ' + f for f in args['changed_files'])}

## 受影响的 Wiki 章节
{args['affected_sections']}

## Diff 文件目录
{args['diffs_dir']}

请逐一阅读 {args['diffs_dir']} 目录下的 diff 文件，分析每个代码变更对 wiki 文档的影响。

输出要求：
- 每个变更文件单独一段分析
- 说明：变更了什么 → 影响哪个 wiki 页面 → 大致需要如何更新
- 如果某个文件不影响 wiki，标记为 "no wiki impact"
''', {
    'label': 'diff analysis',
    'agent': 'diff-analyzer',
})

# ——— Phase 2: 制定更新计划（结构化输出，供 Writer 阶段并行消费） ———
phase('Plan')
plan = await agent(f'''
基于以下分析，为每个需要更新 wiki 的文件生成具体的操作指令：

{analysis if analysis else '(分析阶段未产出结果)'}

要求：
1. 对每个有实际 wiki 影响的变更文件，生成一条任务
2. 同一 wiki 页面的多个文件修改，合并为一条任务
3. 调用 structured_output 工具返回结果
''', {
    'label': 'wiki planning',
    'agent': 'wiki-planner',
    'schema': {
        'type': 'object',
        'properties': {
            'file_tasks': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'file': {'type': 'string'},
                        'wiki_page': {'type': 'string'},
                        'section': {'type': 'string'},
                        'action': {'type': 'string', 'enum': ['create', 'update', 'delete']},
                        'instructions': {'type': 'string'},
                    },
                    'required': ['file', 'wiki_page', 'instructions', 'action'],
                },
            },
            'no_change_files': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Files that have no wiki impact',
            },
        },
        'required': ['file_tasks'],
    },
})

# ——— Phase 3: 并行执行所有 wiki 更新任务 ———
phase('Write')
if plan is None or not isinstance(plan, dict):
    return {
        'phase1_analysis': analysis,
        'phase2_plan': plan,
        'phase3_write': {'total_tasks': 0, 'succeeded': 0, 'failed': 1, 'error': 'Plan agent returned None or invalid type', 'results': []},
    }

tasks = plan.get('file_tasks', [])

if len(tasks) == 0:
    return {
        'phase1_analysis': analysis,
        'phase2_plan': plan,
        'phase3_write': {'total_tasks': 0, 'succeeded': 0, 'failed': 0, 'results': []},
    }

write_results = await parallel([
    lambda task=task: agent(f'''
## 任务
源文件: {task['file']}
目标 Wiki 页面: {task['wiki_page']}
目标章节: {task.get('section', '全局')}
操作类型: {task['action']}
修改指令: {task['instructions']}

## 项目上下文
项目路径: {args['project_path']}
Diff 文件目录: {args['diffs_dir']}

请根据上述指令修改对应的 wiki 页面。完成后简要说明做了什么修改。
''', {
        'label': f"write-{task['wiki_page'].replace('/', '-').replace('.', '-')}",
        'agent': 'wiki-writer',
    })
    for task in tasks
])

# ——— 汇总 ———
succeeded = [r for r in write_results if r is not None]
failed = len(write_results) - len(succeeded)

return {
    'phase1_analysis': analysis,
    'phase2_plan': plan,
    'phase3_write': {
        'total_tasks': len(tasks),
        'succeeded': len(succeeded),
        'failed': failed,
        'results': write_results,
    },
}
