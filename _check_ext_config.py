# Check extension loader for discovery paths
with open('packages/coding-agent/src/pi_coding_agent/core/extensions/loader.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find relevant sections
import re

# Find discovery paths
for m in re.finditer(r'(discover|DISCOVERY|scan|SCAN|\.pi|extensions?)[^\n]*', content):
    line = m.group().strip()
    if line:
        print(line[:200])
