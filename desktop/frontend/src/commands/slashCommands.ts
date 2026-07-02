import type { CompletionItem } from "../hooks/useAutocomplete";

export interface SlashCommand {
  name: string;
  description: string;
  handler: (args: string, context: CommandContext) => void | Promise<void>;
}

export interface CommandContext {
  sessionId: string | null;
  addSystemMessage: (text: string) => void;
  clearMessages: () => void;
  openSettings: () => void;
}

export function getBuiltinCommands(): SlashCommand[] {
  return [
    {
      name: "/help",
      description: "显示所有可用命令",
      handler: (_args, ctx) => {
        const text = buildHelpText();
        ctx.addSystemMessage(text);
      },
    },
    {
      name: "/clear",
      description: "清空当前对话",
      handler: (_args, ctx) => {
        ctx.clearMessages();
      },
    },
    {
      name: "/model",
      description: "查看或切换当前模型",
      handler: async (_args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          await api.cycleModel(ctx.sessionId);
          ctx.addSystemMessage("已切换到下一个模型");
        } catch {
          ctx.addSystemMessage("切换模型失败");
        }
      },
    },
    {
      name: "/compact",
      description: "压缩对话上下文以节省 tokens",
      handler: async (_args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          const result = await api.compact(ctx.sessionId);
          ctx.addSystemMessage(`上下文已压缩 ${result.summary || ""}`);
        } catch {
          ctx.addSystemMessage("压缩上下文失败");
        }
      },
    },
    {
      name: "/thinking",
      description: "切换思考级别 (关闭/极简/低/中/高)",
      handler: async (_args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          const result = await api.cycleThinking(ctx.sessionId);
          ctx.addSystemMessage(`思考级别：${result.thinking_level}`);
        } catch {
          ctx.addSystemMessage("切换思考级别失败");
        }
      },
    },
    {
      name: "/session",
      description: "显示会话统计信息",
      handler: async (_args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          const info = await api.getSession(ctx.sessionId);
          ctx.addSystemMessage(
            `**会话信息**\nID: ${info.session_id}\n消息数: ${info.message_count}\n模型: ${info.model || "无"}`
          );
        } catch {
          ctx.addSystemMessage("获取会话信息失败");
        }
      },
    },
    {
      name: "/tools",
      description: "列出可用工具",
      handler: async (_args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          const result = await api.getTools(ctx.sessionId);
          ctx.addSystemMessage(`**可用工具**：${result.tools.join(", ")}`);
        } catch {
          ctx.addSystemMessage("获取工具列表失败");
        }
      },
    },
    {
      name: "/settings",
      description: "打开设置面板",
      handler: (_args, ctx) => {
        ctx.openSettings();
      },
    },
    {
      name: "/new",
      description: "创建新会话",
      handler: async (_args, ctx) => {
        try {
          const { api } = await import("../services/api");
          const result = await api.createSession();
          ctx.addSystemMessage(`新会话已创建：${result.session_id}`);
        } catch {
          ctx.addSystemMessage("创建会话失败");
        }
      },
    },
    {
      name: "/fork",
      description: "从消息节点分叉对话 (可选: /fork <entry_id>)",
      handler: async (args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          const entryId = args?.trim() || undefined;
          const result = await api.forkSession(ctx.sessionId, entryId);
          ctx.addSystemMessage(`已分叉会话：${result.session_id}${entryId ? ` (于 ${entryId.slice(0, 8)})` : ""}`);
        } catch {
          ctx.addSystemMessage("分叉会话失败");
        }
      },
    },
    {
      name: "/tree",
      description: "查看当前会话的对话树",
      handler: async (_args, ctx) => {
        if (!ctx.sessionId) return;
        try {
          const { api } = await import("../services/api");
          const data = await api.getSessionTree(ctx.sessionId);
          const tree = data.tree || [];
          if (tree.length === 0) {
            ctx.addSystemMessage("对话树为空。发送消息以构建对话树。");
            return;
          }
          const fmt = formatTree(tree, 0);
          ctx.addSystemMessage(`**对话树结构：**\n\`\`\`\n${fmt}\n\`\`\``);
        } catch {
          ctx.addSystemMessage("获取对话树失败");
        }
      },
    },
    {
      name: "/resume",
      description: "切换到另一个会话 (用法: /resume <session_id>)",
      handler: async (args, ctx) => {
        if (!ctx.sessionId) return;
        const query = args?.trim();
        if (!query) {
          // Show session list with IDs
          try {
            const { api } = await import("../services/api");
            const sessions = await api.listSessions();
            if (sessions.length === 0) {
              ctx.addSystemMessage("暂无其他会话。");
              return;
            }
            const lines = sessions.map((s: any) =>
              `- \`${s.session_id.slice(0, 8)}...\` — ${(s.label || s.cwd?.split(/[/\\]/).pop() || "未命名")} (${s.message_count || 0} 条消息)`
            );
            ctx.addSystemMessage(`**可用会话：**\n${lines.join("\n")}\n\n使用 \`/resume <id前缀>\` 切换。`);
          } catch {
            ctx.addSystemMessage("获取会话列表失败");
          }
          return;
        }
        try {
          const { api } = await import("../services/api");
          const sessions = await api.listSessions();
          const match = sessions.find((s: any) => s.session_id.startsWith(query));
          if (match) {
            ctx.addSystemMessage(`已切换到会话：${match.session_id.slice(0, 8)}... (点击侧边栏切换)`);
          } else {
            ctx.addSystemMessage(`未找到匹配的会话：${query}`);
          }
        } catch {
          ctx.addSystemMessage("切换会话失败");
        }
      },
    },
  ];
}

function buildHelpText(): string {
  const cmds = getBuiltinCommands();
  const lines = ["**可用命令：**", ""];
  for (const cmd of cmds) {
    lines.push(`- \`${cmd.name}\` — ${cmd.description}`);
  }
  return lines.join("\n");
}

export function getCommandCompletions(): CompletionItem[] {
  return getBuiltinCommands().map((c) => ({ name: c.name, description: c.description }));
}

function formatTree(nodes: any[], depth: number): string {
  let result = "";
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    const isLast = i === nodes.length - 1;
    const prefix = depth === 0 ? "" : "  ".repeat(depth - 1) + (isLast ? "└─ " : "├─ ");
    const role = node.entry?.data?.role || node.entry?.type || "?";
    const label = node.label ? ` [${node.label}]` : "";
    const branchInfo = node.children?.length > 1 ? ` (${node.children.length} branches)` : "";
    result += `${prefix}${role}${label}${branchInfo} \`${node.entry?.id?.slice(0, 4)}\`\n`;
    if (node.children?.length > 0) {
      result += formatTree(node.children, depth + 1);
    }
  }
  return result;
}
