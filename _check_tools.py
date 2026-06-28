import re

# Check todos
with open('extensions/todos.py', 'r', encoding='utf-8') as f:
    content = f.read()

todos_tools = re.findall(r'register_tool\([^)]+\)|register_command\([^)]+\)', content)
print('=== todos tools/commands ===')
for t in todos_tools:
    print('  ', t[:150])

# Check dag_tasks
with open('extensions/dag_tasks/dag_tasks.py', 'r', encoding='utf-8') as f:
    content = f.read()

dag_tools = re.findall(r'register_tool\([^)]+\)|register_command\([^)]+\)', content)
print('\n=== dag_tasks tools/commands ===')
for t in dag_tools:
    print('  ', t[:150])
