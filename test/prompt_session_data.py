"""
端到端测试: 使用 create_agent_session (同 main.py 方式) 创建 session,
通过真实模型调用验证 session_data 在 ExtensionRunner 各位置可获取。

运行: .venv/Scripts/python.exe test/prompt_session_data.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "ai", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "agent", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "coding-agent", "src"))

from dotenv import load_dotenv

from pi_coding_agent.core.sdk import create_agent_session, CreateAgentSessionOptions
from pi_coding_agent.core.auth_storage import AuthStorage
from pi_coding_agent.core.model_registry import ModelRegistry
from pi_coding_agent.core.session_manager import SessionManager
from pi_coding_agent.core.settings_manager import SettingsManager
from pi_coding_agent.core.extensions.types import Extension, ExtensionAPI
from pi_coding_agent.core.extensions.runner import ExtensionRunner
from pi_coding_agent.core.extensions.wrapper import wrap_tools_with_extensions


def get_agent_dir() -> str | None:
    return os.environ.get("PI_AGENT_DIR")


async def main():
    # ── 加载环境 ──
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    cwd = os.getcwd()

    # ── 同 main.py 的初始化 ──
    settings_manager = SettingsManager.create(cwd, get_agent_dir())
    auth_storage = AuthStorage()
    model_registry = ModelRegistry()
    session_manager = SessionManager.create(cwd)

    # 如果 .env 只有 DEEPSEEK_API_KEY 没有 OPENROUTER_API_KEY, 注入给 openrouter
    if not os.environ.get("OPENROUTER_API_KEY"):
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            auth_storage.set_runtime_api_key("openrouter", deepseek_key)
            print(f"[setup] DEEPSEEK_API_KEY → openrouter")

    # ── 模型: 优先用 settings 配置, 否则走 OpenRouter DeepSeek ──
    try:
        model = model_registry.resolve_model(
            model_id=settings_manager.get_default_model(),
            provider=settings_manager.get_default_provider(),
        )
    except Exception:
        from pi_ai import get_model
        model = get_model("openrouter", "deepseek/deepseek-chat")

    print(f"[setup] model: {model.provider}/{model.id}")

    # ── 创建 guard 扩展 ──
    guard_ext = Extension(path="guard_ext", resolved_path="/test/guard")
    guard_api = ExtensionAPI(guard_ext)

    async def guard_tool_call(ctx, event):
        tool_name = event.get("tool_name", "")
        editable_ids = ctx.metadata.get("editable_session_ids", [])
        sid = ctx.session_id
        print(f"\n{'─' * 40}")
        print(f"[guard tool_call] tool={tool_name}")
        print(f"[guard tool_call] session_id={sid}")
        print(f"[guard tool_call] editable_ids={editable_ids}")
        print(f"[guard tool_call] 可编辑: {sid in editable_ids}")
        print(f"{'─' * 40}\n")
        if tool_name == "edit" and editable_ids and sid not in editable_ids:
            return {"block": True, "reason": f"Edit blocked for session {sid}"}

    async def guard_tool_result(ctx, event):
        print(f"\n{'─' * 40}")
        print(f"[guard tool_result] tool={event.get('tool_name')}")
        print(f"[guard tool_result] session_id={ctx.session_id}")
        print(f"[guard tool_result] metadata keys={list(ctx.metadata.keys())}")
        print(f"{'─' * 40}\n")

    async def on_context(ctx, event):
        msgs = event.get("messages", [])
        print(f"[guard context] session={ctx.session_id}, messages={len(msgs)}, "
              f"metadata_keys={list(ctx.metadata.keys())}")

    guard_api.on("tool_call", guard_tool_call)
    guard_api.on("tool_result", guard_tool_result)
    guard_api.on("context", on_context)

    # ── 按 main.py 方式: CreateAgentSessionOptions → create_agent_session ──
    opts = CreateAgentSessionOptions(
        cwd=cwd,
        model=model,
        thinking_level=settings_manager.get_default_thinking_level() or "off",
        session_manager=session_manager,
        auth_storage=auth_storage,
        model_registry=model_registry,
        settings_manager=settings_manager,
    )
    result = await create_agent_session(opts)
    session = result.session

    current_sid = session.session_id
    print(f"[setup] session_id: {current_sid}")
    print(f"[setup] tools: {[t.name for t in session._all_tools]}")

    # ── 注入 guard 扩展到 ExtensionRunner ──
    if session._extension_runner is None:
        runner = ExtensionRunner([guard_ext], cwd=cwd, session_id=current_sid)
        session._extension_runner = runner
        session._all_tools = wrap_tools_with_extensions(session._all_tools, runner)
        session._agent.set_tools(session._all_tools)
        print("[setup] 创建新 ExtensionRunner + guard 扩展")
    else:
        session._extension_runner._extensions.append(guard_ext)
        print("[setup] guard 扩展已加入现有 ExtensionRunner")

    print(f"[setup] runner.has_handlers('tool_call'): {session._extension_runner.has_handlers('tool_call')}")

    # ── 发送 prompt ──
    print("\n>>> 发送 prompt (当前 session 在可编辑列表中)...\n")
    await session.prompt(
        "帮我在当前目录创建一个 test.md 文件, 内容写 'hello world'",
        session_data={"editable_session_ids": [current_sid]},
    )

    # ── 查看结果 ──
    print(f"\n[result] 消息数量: {len(session.state.messages)}")
    test_file = os.path.join(cwd, "test.md")
    if os.path.exists(test_file):
        with open(test_file) as f:
            print(f"[result] test.md 内容: {f.read()}")
    else:
        print("[result] test.md 不存在")


if __name__ == "__main__":
    asyncio.run(main())
