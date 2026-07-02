import { create } from "zustand";
import type { ChatMessage, ToolCallEntry } from "../types/events";
import type { AgentEvent } from "../types/events";

interface StreamingState {
  content: string;
  thinking: string;
  pendingToolCalls: Map<string, ToolCallEntry>;
}

interface ChatState {
  messages: ChatMessage[];
  streaming: StreamingState | null;
  isStreaming: boolean;
  contextUsage: { tokens: number; contextWindow: number; percent: number } | null;

  addMessage: (msg: ChatMessage) => void;
  setMessages: (msgs: ChatMessage[]) => void;
  clearMessages: () => void;
  setStreaming: (s: StreamingState | null) => void;
  setIsStreaming: (v: boolean) => void;
  setContextUsage: (u: { tokens: number; contextWindow: number; percent: number } | null) => void;
  handleEvent: (event: AgentEvent) => void;
}

let msgSeq = 0;
function nextId(): string {
  return `msg-${Date.now()}-${++msgSeq}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streaming: null,
  isStreaming: false,
  contextUsage: null,

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  clearMessages: () => set({ messages: [], streaming: null }),
  setStreaming: (streaming) => set({ streaming }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  setContextUsage: (u) => set({ contextUsage: u }),

  handleEvent: (event: AgentEvent) => {
    const state = get();
    switch (event.type) {
      case "message_start": {
        if (event.message.role === "assistant") {
          set({
            isStreaming: true,
            streaming: { content: "", thinking: "", pendingToolCalls: new Map() },
          });
        } else if (event.message.role === "user") {
          const userMsg = event.message as Record<string, unknown>;
          if (userMsg.entry_id) {
            const msgs = state.messages;
            if (msgs.length > 0) {
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], entry_id: userMsg.entry_id as string };
              set({ messages: [...msgs] });
            }
          }
        }
        break;
      }
      case "message_update": {
        const s = state.streaming;
        if (!s) return;
        const evt = event.assistant_message_event;
        if (evt.type === "text_delta" && typeof evt.delta === "string") {
          set({ streaming: { ...s, content: s.content + evt.delta } });
        } else if (evt.type === "thinking_delta" && typeof evt.delta === "string") {
          set({ streaming: { ...s, thinking: s.thinking + evt.delta } });
        } else if (evt.type === "full_snapshot" && evt.snapshot) {
          const content = extractText(evt.snapshot.content);
          set({ streaming: { ...s, content } });
        }
        break;
      }
      case "message_end": {
        const cur = state.streaming;
        if (event.message.role === "assistant") {
          // When response is instant, no message_update deltas arrive.
          // Fall back to extracting text from the final message content.
          const deltaContent = cur?.content || "";
          const finalContent = deltaContent || extractText(event.message.content);
          const toolCalls = cur
            ? Array.from(cur.pendingToolCalls.values())
            : [];
          const msg: ChatMessage = {
            id: nextId(),
            role: "assistant",
            content: finalContent,
            thinking: cur?.thinking || undefined,
            toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
            timestamp: Date.now(),
          };
          set((s) => ({
            messages: [...s.messages, msg],
            streaming: null,
            isStreaming: false,
          }));
        }
        break;
      }
      case "tool_execution_start": {
        const s = state.streaming;
        if (!s) return;
        const newMap = new Map(s.pendingToolCalls);
        newMap.set(event.tool_call_id, {
          id: event.tool_call_id,
          name: event.tool_name,
          args: event.args,
          status: "running",
          isError: false,
        });
        set({ streaming: { ...s, pendingToolCalls: newMap } });
        break;
      }
      case "tool_execution_end": {
        const s = state.streaming;
        if (!s) return;
        const newMap = new Map(s.pendingToolCalls);
        const existing = newMap.get(event.tool_call_id);
        if (existing) {
          newMap.set(event.tool_call_id, {
            ...existing,
            result: event.result,
            isError: event.is_error,
            status: "completed",
          });
        }
        set({ streaming: { ...s, pendingToolCalls: newMap } });
        break;
      }
      case "agent_end": {
        set({ isStreaming: false });
        break;
      }
      case "context_usage": {
        set({
          contextUsage: {
            tokens: event.tokens,
            contextWindow: event.contextWindow,
            percent: event.percent,
          },
        });
        break;
      }
      case "error": {
        set({ isStreaming: false });
        break;
      }
    }
  },
}));

function extractText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((b: any) => b?.type === "text")
      .map((b: any) => b.text)
      .join("");
  }
  return "";
}
