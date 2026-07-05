"""
验证 extension_runner hook 管道是否正常工作的端到端测试。

测试链条:
  Extension 加载 → ExtensionRunner 创建 → 工具包装 → 工具执行 → hook 触发
"""
import asyncio
import os
import sys
import tempfile
import json

# 确保包在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "ai", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "agent", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "coding-agent", "src"))

from pi_coding_agent.core.extensions.types import (
    Extension,
    ExtensionAPI,
    ExtensionContext,
)
from pi_coding_agent.core.extensions.runner import ExtensionRunner
from pi_coding_agent.core.extensions.wrapper import wrap_tools_with_extensions


# ── 辅助: 创建模拟的 AgentTool ──────────────────────────────────────────
class FakeAgentTool:
    """模拟 AgentTool，只用到了 execute, name 属性"""
    def __init__(self, name, execute):
        self.name = name
        self.description = ""
        self.parameters = {}
        self.label = name
        self.execute = execute

    def model_copy(self, update=None):
        """模拟 Pydantic model_copy"""
        result = FakeAgentTool(self.name, self.execute)
        if update:
            for k, v in update.items():
                setattr(result, k, v)
        return result


# ── 辅助: 创建模拟的 AgentToolResult ────────────────────────────────────
class FakeAgentToolResult:
    def __init__(self, content, details=None):
        self.content = content
        self.details = details


# ── 测试 1: tool_result hook 在工具执行后被触发 ─────────────────────────
async def test_tool_result_hook_fires():
    """验证: 注册 tool_result handler 后, 工具执行完毕 handler 被调用"""
    hook_fired = False
    received_tool_name = None
    received_file_path = None

    # 1. 创建扩展, 注册 tool_result handler
    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)

    async def on_tool_result(ctx, event):
        nonlocal hook_fired, received_tool_name, received_file_path
        hook_fired = True
        received_tool_name = event.get("tool_name", "")
        received_file_path = event.get("input", {}).get("file_path", "")

    api.on("tool_result", on_tool_result)

    # 2. 创建 ExtensionRunner
    runner = ExtensionRunner([ext], cwd="/test", session_id="test-session")

    # 3. 创建模拟工具
    async def fake_edit(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(
            content=[{"type": "text", "text": "diff: added 3 lines"}],
            details={"lines_added": 3},
        )

    tool = FakeAgentTool(name="edit", execute=fake_edit)

    # 4. 包装工具
    [wrapped] = wrap_tools_with_extensions([tool], runner)

    # 5. 执行工具
    result = await wrapped.execute(
        "call-001",
        {"file_path": "docs/test.md", "old_string": "a", "new_string": "b"},
        None,
        None,
    )

    # 6. 断言
    assert hook_fired, "FAIL: tool_result hook 没有被触发"
    assert received_tool_name == "edit", f"FAIL: tool_name 应为 'edit', 实际 '{received_tool_name}'"
    assert received_file_path == "docs/test.md", f"FAIL: file_path 应为 'docs/test.md', 实际 '{received_file_path}'"
    assert "added 3 lines" in str(result.content), "FAIL: 原始工具结果应保留"

    print("PASS: test_tool_result_hook_fires")


# ── 测试 2: tool_result hook 可以修改返回内容 ───────────────────────────
async def test_tool_result_hook_modifies_content():
    """验证: handler 返回 content 可以追加到工具结果中"""
    # 1. 创建扩展
    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)

    async def on_tool_result(ctx, event):
        original = event.get("content", [])
        check_block = {"type": "text", "text": "\n[Wiki Guard] 发现 2 个断链"}
        return {"content": original + [check_block]}

    api.on("tool_result", on_tool_result)

    # 2. Runner + 工具
    runner = ExtensionRunner([ext], cwd="/test", session_id="test-session")

    async def fake_edit(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(
            content=[{"type": "text", "text": "File edited successfully."}],
        )

    tool = FakeAgentTool(name="edit", execute=fake_edit)
    [wrapped] = wrap_tools_with_extensions([tool], runner)

    # 3. 执行
    result = await wrapped.execute("call-002", {"file_path": "test.md"}, None, None)

    # 4. 断言: 原始内容 + 检查报告都存在
    texts = [c["text"] for c in result.content if c["type"] == "text"]
    combined = " ".join(texts)
    assert "File edited successfully." in combined, "FAIL: 原始内容丢失"
    assert "Wiki Guard" in combined, "FAIL: hook 追加的内容丢失"
    assert "断链" in combined, "FAIL: 中文检查报告未出现"

    print("PASS: test_tool_result_hook_modifies_content")


# ── 测试 3: tool_call hook 可以阻断工具执行 ──────────────────────────────
async def test_tool_call_hook_blocks():
    """验证: tool_call handler 返回 {block: True} 可以阻断工具执行"""
    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)

    async def on_tool_call(ctx, event):
        file_path = event.get("input", {}).get("file_path", "")
        if "forbidden" in file_path:
            return {"block": True, "reason": "禁止修改此文件"}

    api.on("tool_call", on_tool_call)

    runner = ExtensionRunner([ext], cwd="/test", session_id="test-session")

    executed = False
    async def fake_edit(tool_call_id, params, cancel_event, on_update):
        nonlocal executed
        executed = True
        return FakeAgentToolResult(content=[{"type": "text", "text": "ok"}])

    tool = FakeAgentTool(name="edit", execute=fake_edit)
    [wrapped] = wrap_tools_with_extensions([tool], runner)

    # 阻断场景
    try:
        await wrapped.execute("call-003", {"file_path": "forbidden.md"}, None, None)
        assert False, "FAIL: 应该抛出 RuntimeError"
    except RuntimeError as e:
        assert "禁止修改此文件" in str(e), f"FAIL: 错误消息不匹配: {e}"
        assert not executed, "FAIL: 工具不应该被执行"

    # 正常场景
    result = await wrapped.execute("call-004", {"file_path": "allowed.md"}, None, None)
    assert executed, "FAIL: 正常文件应该允许执行"

    print("PASS: test_tool_call_hook_blocks")


# ── 测试 4: 无 handler 时包装零开销 ──────────────────────────────────────
async def test_no_handlers_no_overhead():
    """验证: 没有扩展注册 handler 时, 工具正常执行, 结果不被修改"""
    ext = Extension(path="empty_ext", resolved_path="/test/empty")
    # 不注册任何 handler
    runner = ExtensionRunner([ext], cwd="/test", session_id="test-session")

    async def fake_write(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(content=[{"type": "text", "text": "File written."}])

    tool = FakeAgentTool(name="write", execute=fake_write)
    [wrapped] = wrap_tools_with_extensions([tool], runner)

    result = await wrapped.execute("call-005", {"path": "test.md"}, None, None)
    texts = [c["text"] for c in result.content if c["type"] == "text"]
    assert texts == ["File written."], f"FAIL: 结果被意外修改: {texts}"

    print("PASS: test_no_handlers_no_overhead")


# ── 测试 5: 工具抛出异常时 tool_result 仍可捕获 ─────────────────────────
async def test_error_handling():
    """验证: 工具抛出异常时, tool_result 以 is_error=True 触发"""
    error_captured = False
    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)

    async def on_tool_result(ctx, event):
        nonlocal error_captured
        if event.get("is_error"):
            error_captured = True

    api.on("tool_result", on_tool_result)

    runner = ExtensionRunner([ext], cwd="/test", session_id="test-session")

    async def broken_tool(tool_call_id, params, cancel_event, on_update):
        raise ValueError("模拟工具崩溃")

    tool = FakeAgentTool(name="bash", execute=broken_tool)
    [wrapped] = wrap_tools_with_extensions([tool], runner)

    try:
        await wrapped.execute("call-006", {"command": "rm -rf /"}, None, None)
    except ValueError:
        pass  # 预期异常

    assert error_captured, "FAIL: tool_result 应该以 is_error=True 被触发"

    print("PASS: test_error_handling")


# ── 主入口 ──────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("extension_runner hook 管道验证")
    print("=" * 60)
    print()

    tests = [
        test_tool_result_hook_fires,
        test_tool_result_hook_modifies_content,
        test_tool_call_hook_blocks,
        test_no_handlers_no_overhead,
        test_error_handling,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"  {e}")
            failed += 1
        except Exception as e:
            print(f"  UNEXPECTED ERROR in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 项")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
