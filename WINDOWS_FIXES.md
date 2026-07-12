# Windows 兼容性修复总结

本文档记录了为使 `pi-wiki-agent` 在 Windows 上正常工作所做的修复。

## 修复的问题

### 1. API 参数不匹配 ✅
**文件**: `packages/coding-agent/src/pi_coding_agent/main.py`

**问题**: `CreateAgentSessionOptions` 的调用参数与实际定义不匹配
- 传递了不存在的参数：`model_id`, `provider`, `api_key`, `auto_compact`, `sessions_dir`

**修复**: 
- 使用 `model_registry.resolve_model()` 将 `model_id` + `provider` 转换为 `Model` 对象
- 移除不存在的参数
- 正确传递 `model`, `session_manager`, `settings_manager` 等参数

### 2. DeepSeek API 密钥环境变量映射 ✅
**文件**: `packages/ai/src/pi_ai/env_api_keys.py`

**问题**: `DEEPSEEK_API_KEY` 环境变量未注册

**修复**: 在 `PROVIDER_ENV_VARS` 字典中添加：
```python
"deepseek": "DEEPSEEK_API_KEY",
```

### 3. DeepSeek 不支持 `developer` 角色 ✅
**文件**: 
- `packages/ai/src/pi_ai/providers/openai_completions.py`
- `packages/ai/src/pi_ai/providers/openai_responses_shared.py`

**问题**: DeepSeek API 不接受 `developer` 角色，只支持 `system`, `user`, `assistant`

**修复**: 修改 `_uses_developer_role()` 函数和相关逻辑，检查模型的 `compat.supports_developer_role` 属性：
```python
def _uses_developer_role(model: Model) -> bool:
    if not getattr(model, "reasoning", False):
        return False
    compat = getattr(model, "compat", None)
    if compat is not None:
        if isinstance(compat, dict):
            if compat.get("supportsDeveloperRole") is False:
                return False
        elif hasattr(compat, "supports_developer_role"):
            if getattr(compat, "supports_developer_role") is False:
                return False
    return True
```

**配置**: 在 `~/.pi/agent/models.json` 中为 DeepSeek 模型添加：
```json
"compat": {
    "supportsDeveloperRole": false,
    ...
}
```

### 4. Readline 模式事件处理 ✅
**文件**: `packages/coding-agent/src/pi_coding_agent/modes/interactive/mode.py`

**问题**: 
- 使用 `sys.stdin.readline()` 在某些情况下无法工作
- 事件对象是 Pydantic 模型而不是字典，使用 `.get()` 方法失败

**修复**:
1. 将 `sys.stdin.readline()` 替换为 `input()` 函数
2. 修改事件处理以支持字典和对象格式：
```python
def on_event(event: Any) -> None:
    if isinstance(event, dict):
        event_type = event.get("type", "")
    else:
        event_type = getattr(event, "type", "")
    
    if event_type == "message_update":
        # 提取嵌套的 assistant_message_event
        ...
```

### 5. Windows TUI 输入支持 ✅
**文件**: `packages/tui/src/pi_tui/terminal.py`

**问题**: TUI 在 Windows 上无法捕获键盘输入
- `tty` 和 `termios` 模块在 Windows 上不可用
- `select.select()` 在 Windows 上不支持文件描述符

**修复**:

#### 5.1 Windows 控制台模式设置
```python
def _enable_raw_mode(self) -> None:
    if platform.system() == "Windows":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        
        # Get console handles
        h_stdin = kernel32.GetStdHandle(-10)
        h_stdout = kernel32.GetStdHandle(-11)
        
        # Enable virtual terminal input mode
        kernel32.SetConsoleMode(h_stdin, 0x0200)
        kernel32.SetConsoleMode(h_stdout, mode | 0x0004 | 0x0008)
```

#### 5.2 Windows 输入读取循环
```python
if platform.system() == "Windows":
    import msvcrt
    while self._stdin_buffer is not None:
        if msvcrt.kbhit():
            data = msvcrt.getwch()
            if data:
                buf.process(data.encode('utf-8'))
        else:
            time.sleep(0.01)
else:
    # Unix: use select.select()
    ...
```

## 环境变量

### 可选配置
- `PI_FORCE_READLINE=1`: 强制使用简单的 readline 模式（禁用 TUI）
- `PI_INTERACTIVE_TRACE_LOG=<path>`: 启用 TUI 调试日志
- `PYTHONIOENCODING=utf-8`: 解决中文输出的编码问题

## 测试

所有功能现在在 Windows 上正常工作：

```powershell
# 列出可用模型
uv run --package pi-coding-agent pi --list-models

# 非交互式模式
uv run --package pi-coding-agent pi --print "Hello"

# 交互式 TUI 模式
uv run --package pi-coding-agent pi

# 交互式 readline 模式（如需）
$env:PI_FORCE_READLINE="1"
uv run --package pi-coding-agent pi
```

## 已知限制

1. **中文输出中的 emoji**: 如果终端使用 GBK 编码，emoji 字符可能导致编码错误
   - 解决方案: 设置 `$env:PYTHONIOENCODING="utf-8"`

2. **Windows Terminal 推荐**: 在 Windows Terminal 中运行效果最佳

## 文件修改清单

1. `packages/coding-agent/src/pi_coding_agent/main.py` - API 参数修复
2. `packages/ai/src/pi_ai/env_api_keys.py` - DeepSeek 环境变量
3. `packages/ai/src/pi_ai/providers/openai_completions.py` - developer 角色检查
4. `packages/ai/src/pi_ai/providers/openai_responses_shared.py` - developer 角色检查
5. `packages/coding-agent/src/pi_coding_agent/modes/interactive/mode.py` - readline 事件处理
6. `packages/coding-agent/src/pi_coding_agent/modes/interactive/tui.py` - Windows TUI 启用
7. `packages/tui/src/pi_tui/terminal.py` - Windows 原生输入支持

## 贡献者

修复由 Claude (Anthropic) 协助完成，2025年1月
