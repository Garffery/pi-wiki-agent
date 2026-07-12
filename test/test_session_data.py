"""
验证 session_data 是否能在各个执行位置正确获取。

测试链条:
  prompt(session_data={...})
    → ExtensionRunner.set_session_data()
      → emit()        → handler(ctx, event)  → ctx.metadata
      → emit_context() → handler(ctx, event)  → ctx.metadata
      → tool_call      → handler(ctx, event)  → ctx.metadata (via wrapper)
      → tool_result    → handler(ctx, event)  → ctx.metadata (via wrapper)
"""
import asyncio
import os
import sys

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

SAMPLE_DATA = {
    "editable_session_ids": ["sess-001", "sess-003", "sess-007"],
    "project_id": "wiki-proj-42",
    "allowed_tools": ["read", "grep", "find", "ls"],
}


# ── 辅助类 ────────────────────────────────────────────────────────────────

class FakeAgentTool:
    def __init__(self, name, execute):
        self.name = name
        self.description = ""
        self.parameters = {}
        self.label = name
        self.execute = execute

    def model_copy(self, update=None):
        result = FakeAgentTool(self.name, self.execute)
        if update:
            for k, v in update.items():
                setattr(result, k, v)
        return result


class FakeAgentToolResult:
    def __init__(self, content, details=None):
        self.content = content
        self.details = details


# ── 测试 1: emit() 中 handler 能通过 ctx.metadata 获取 session_data ───────

async def test_session_data_in_emit():
    """验证: ExtensionRunner.emit() 触发 handler 时, ctx.metadata 包含 session_data"""
    print("\n─── 测试 1: emit() → ctx.metadata ───")

    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)
    received_metadata = {}

    async def handler(ctx, event):
        nonlocal received_metadata
        received_metadata = ctx.metadata
        print(f"  [emit handler] ctx.session_id = {ctx.session_id}")
        print(f"  [emit handler] ctx.metadata    = {ctx.metadata}")

    api.on("custom_event", handler)

    runner = ExtensionRunner([ext], cwd="/test/project", session_id="sess-003")
    runner.set_session_data(SAMPLE_DATA)

    await runner.emit({"type": "custom_event", "payload": "hello"})

    assert received_metadata == SAMPLE_DATA, \
        f"FAIL: ctx.metadata 未正确传递。期望 {SAMPLE_DATA}, 实际 {received_metadata}"
    assert received_metadata["editable_session_ids"] == ["sess-001", "sess-003", "sess-007"]
    assert "sess-003" in received_metadata["editable_session_ids"], \
        "FAIL: 当前 session 'sess-003' 应在 editable_session_ids 中"

    print("  PASS: emit() → ctx.metadata 正确传递")


# ── 测试 2: emit_context() 中 handler 能通过 ctx.metadata 获取 session_data ──

async def test_session_data_in_emit_context():
    """验证: ExtensionRunner.emit_context() 触发 handler 时, ctx.metadata 包含 session_data"""
    print("\n─── 测试 2: emit_context() → ctx.metadata ───")

    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)
    received_metadata = {}

    async def context_handler(ctx, event):
        nonlocal received_metadata
        received_metadata = ctx.metadata
        print(f"  [context handler] ctx.session_id = {ctx.session_id}")
        print(f"  [context handler] ctx.metadata    = {ctx.metadata}")
        print(f"  [context handler] event.messages count = {len(event.get('messages', []))}")
        return {"messages": event.get("messages", [])}

    api.on("context", context_handler)

    runner = ExtensionRunner([ext], cwd="/test/project", session_id="sess-001")
    runner.set_session_data(SAMPLE_DATA)

    test_messages = [{"role": "user", "content": "hello"}]
    result = await runner.emit_context(test_messages)

    assert received_metadata == SAMPLE_DATA, \
        f"FAIL: ctx.metadata 未正确传递。期望 {SAMPLE_DATA}, 实际 {received_metadata}"
    assert result == test_messages, "FAIL: emit_context 应返回原始消息"

    print("  PASS: emit_context() → ctx.metadata 正确传递")


# ── 测试 3: tool_call 拦截中 handler 能通过 ctx.metadata 获取 session_data ──

async def test_session_data_in_tool_call():
    """验证: 工具执行前, tool_call handler 的 ctx.metadata 包含 session_data"""
    print("\n─── 测试 3: tool_call → ctx.metadata ───")

    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)
    received_metadata = {}
    received_tool_name = None

    async def on_tool_call(ctx, event):
        nonlocal received_metadata, received_tool_name
        received_metadata = ctx.metadata
        received_tool_name = event.get("tool_name", "")
        print(f"  [tool_call handler] ctx.session_id  = {ctx.session_id}")
        print(f"  [tool_call handler] ctx.metadata     = {ctx.metadata}")
        print(f"  [tool_call handler] event.tool_name  = {received_tool_name}")

        # 模拟 guard 检查逻辑
        editable_ids = ctx.metadata.get("editable_session_ids", [])
        if received_tool_name == "edit" and ctx.session_id not in editable_ids:
            return {"block": True, "reason": f"Edit blocked: session {ctx.session_id} not in editable list"}

    api.on("tool_call", on_tool_call)

    runner = ExtensionRunner([ext], cwd="/test/project", session_id="sess-999")
    runner.set_session_data(SAMPLE_DATA)

    # ── 场景 A: session 不在可编辑列表中, edit 工具应被阻断 ──
    print("  [场景 A] session=sess-999 (不在列表中), tool=edit → 应阻断")
    async def fake_edit(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(content=[{"type": "text", "text": "edited"}])

    tool_edit = FakeAgentTool(name="edit", execute=fake_edit)
    [wrapped_edit] = wrap_tools_with_extensions([tool_edit], runner)

    try:
        await wrapped_edit.execute("call-001", {"file_path": "docs/test.md"}, None, None)
        assert False, "FAIL: edit 应被阻断"
    except RuntimeError as e:
        assert "not in editable list" in str(e), f"FAIL: 阻断原因不匹配: {e}"
        print(f"  [场景 A] 正确阻断: {e}")

    assert received_metadata == SAMPLE_DATA, \
        f"FAIL: tool_call handler 的 ctx.metadata 未正确传递。期望 {SAMPLE_DATA}, 实际 {received_metadata}"

    # ── 场景 B: session 在可编辑列表中, edit 工具应正常执行 ──
    print("  [场景 B] session=sess-003 (在列表中), tool=edit → 应放行")
    runner2 = ExtensionRunner([ext], cwd="/test/project", session_id="sess-003")
    runner2.set_session_data(SAMPLE_DATA)

    tool_edit2 = FakeAgentTool(name="edit", execute=fake_edit)
    [wrapped_edit2] = wrap_tools_with_extensions([tool_edit2], runner2)

    result = await wrapped_edit2.execute("call-002", {"file_path": "docs/test.md"}, None, None)
    assert "edited" in str(result.content), "FAIL: edit 应正常执行"
    print(f"  [场景 B] 正常执行, 结果: {result.content}")

    print("  PASS: tool_call → ctx.metadata 正确传递, guard 逻辑生效")


# ── 测试 4: tool_result 拦截中 handler 能通过 ctx.metadata 获取 session_data ──

async def test_session_data_in_tool_result():
    """验证: 工具执行后, tool_result handler 的 ctx.metadata 包含 session_data"""
    print("\n─── 测试 4: tool_result → ctx.metadata ───")

    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)
    received_metadata = {}

    async def on_tool_result(ctx, event):
        nonlocal received_metadata
        received_metadata = ctx.metadata
        print(f"  [tool_result handler] ctx.session_id = {ctx.session_id}")
        print(f"  [tool_result handler] ctx.metadata    = {ctx.metadata}")
        print(f"  [tool_result handler] event.tool_name = {event.get('tool_name', '')}")

        # 追加 session 信息到结果中
        original = event.get("content", [])
        info = {
            "type": "text",
            "text": f"\n[SessionData] project={ctx.metadata.get('project_id')}, "
                    f"editable_sessions={ctx.metadata.get('editable_session_ids')}"
        }
        return {"content": original + [info]}

    api.on("tool_result", on_tool_result)

    runner = ExtensionRunner([ext], cwd="/test/project", session_id="sess-007")
    runner.set_session_data(SAMPLE_DATA)

    async def fake_read(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(content=[{"type": "text", "text": "file content here"}])

    tool_read = FakeAgentTool(name="read", execute=fake_read)
    [wrapped_read] = wrap_tools_with_extensions([tool_read], runner)

    result = await wrapped_read.execute("call-003", {"file_path": "README.md"}, None, None)

    assert received_metadata == SAMPLE_DATA, \
        f"FAIL: tool_result handler 的 ctx.metadata 未正确传递"

    texts = [c["text"] for c in result.content if c["type"] == "text"]
    combined = " ".join(texts)
    assert "file content here" in combined, "FAIL: 原始结果丢失"
    assert "wiki-proj-42" in combined, f"FAIL: session_data 中的 project_id 未出现在结果中, got: {combined}"
    print(f"  [tool_result] 最终内容包含 session_data 标记: {combined}")

    print("  PASS: tool_result → ctx.metadata 正确传递")


# ── 测试 5: 无 session_data 时的默认行为 ──

async def test_no_session_data_defaults():
    """验证: 不传 session_data 时, ctx.metadata 为空 dict, 不影响正常流程"""
    print("\n─── 测试 5: 无 session_data 时的默认行为 ───")

    ext = Extension(path="test_ext", resolved_path="/test/ext")
    api = ExtensionAPI(ext)
    received_metadata = None

    async def handler(ctx, event):
        nonlocal received_metadata
        received_metadata = ctx.metadata
        print(f"  [handler] ctx.metadata = {ctx.metadata} (type: {type(ctx.metadata).__name__})")

    api.on("test_event", handler)

    runner = ExtensionRunner([ext], cwd="/test", session_id="sess-001")
    # 故意不调用 set_session_data

    await runner.emit({"type": "test_event"})

    assert received_metadata == {}, \
        f"FAIL: 未传 session_data 时 ctx.metadata 应为空 dict, 实际 {received_metadata}"

    print("  PASS: 无 session_data 时 ctx.metadata 为空 dict")


# ── 测试 6: 完整拦截链路模拟 ──

async def test_full_guard_pipeline():
    """验证: 从 prompt() 设置 session_data → tool_call 拦截 → tool_result 追加 的完整链路"""
    print("\n─── 测试 6: 完整拦截链路 ───")

    # 模拟 AgentSession.prompt() 的行为
    session_id = "sess-005"
    session_data = {
        "editable_session_ids": ["sess-001", "sess-002"],  # sess-005 不在列表中!
        "project_id": "wiki-demo",
    }

    # 注册 tool_call guard 和 tool_result hook
    ext = Extension(path="guard_ext", resolved_path="/test/guard")
    api = ExtensionAPI(ext)

    blocked_calls = []
    allowed_calls = []
    results_with_metadata = []

    async def guard_tool_call(ctx, event):
        tool_name = event.get("tool_name", "")
        editable_ids = ctx.metadata.get("editable_session_ids", [])
        current_sid = ctx.session_id

        print(f"  [guard] tool={tool_name}, session={current_sid}, editable_ids={editable_ids}")

        if tool_name == "edit":
            if editable_ids and current_sid not in editable_ids:
                blocked_calls.append(tool_name)
                return {"block": True, "reason": f"Edit blocked for session {current_sid}"}
            allowed_calls.append(tool_name)

    async def audit_tool_result(ctx, event):
        results_with_metadata.append({
            "tool": event.get("tool_name"),
            "session": ctx.session_id,
            "project": ctx.metadata.get("project_id"),
        })
        print(f"  [audit] tool={event.get('tool_name')}, project={ctx.metadata.get('project_id')}")

    api.on("tool_call", guard_tool_call)
    api.on("tool_result", audit_tool_result)

    runner = ExtensionRunner([ext], cwd="/test/project", session_id=session_id)
    runner.set_session_data(session_data)

    # ── 执行 edit (应被阻断) ──
    async def fake_edit(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(content=[{"type": "text", "text": "edited"}])

    async def fake_read(tool_call_id, params, cancel_event, on_update):
        return FakeAgentToolResult(content=[{"type": "text", "text": "content"}])

    tool_edit = FakeAgentTool(name="edit", execute=fake_edit)
    tool_read = FakeAgentTool(name="read", execute=fake_read)
    [wrapped_edit, wrapped_read] = wrap_tools_with_extensions([tool_edit, tool_read], runner)

    # edit → 应阻断
    try:
        await wrapped_edit.execute("call-e1", {"file_path": "secret.md"}, None, None)
        assert False, "FAIL: edit 应被阻断"
    except RuntimeError:
        pass

    # read → 应正常
    result = await wrapped_read.execute("call-r1", {"file_path": "readme.md"}, None, None)

    # ── 断言 ──
    assert len(blocked_calls) == 1 and "edit" in blocked_calls, \
        f"FAIL: edit 应被阻断, blocked={blocked_calls}"
    assert len(results_with_metadata) == 1, \
        f"FAIL: read 的 tool_result 应触发, results={results_with_metadata}"
    assert results_with_metadata[0]["project"] == "wiki-demo", \
        "FAIL: tool_result handler 应拿到 project_id"
    assert results_with_metadata[0]["session"] == "sess-005", \
        "FAIL: tool_result handler 应拿到 session_id"

    print(f"  blocked: {blocked_calls}")
    print(f"  results with metadata: {results_with_metadata}")
    print("  PASS: 完整拦截链路验证通过")


# ── 主入口 ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("session_data 传递路径验证")
    print(f"sample_data = {SAMPLE_DATA}")
    print("=" * 60)

    tests = [
        test_session_data_in_emit,
        test_session_data_in_emit_context,
        test_session_data_in_tool_call,
        test_session_data_in_tool_result,
        test_no_session_data_defaults,
        test_full_guard_pipeline,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
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
