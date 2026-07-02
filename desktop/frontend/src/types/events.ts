/** Agent event types received over WebSocket */

export interface AgentEventBase {
  type: string;
  sequence?: number;
}

export interface AgentEventAgentStart extends AgentEventBase {
  type: "agent_start";
}

export interface AgentEventAgentEnd extends AgentEventBase {
  type: "agent_end";
  messages: unknown[];
}

export interface AgentEventTurnStart extends AgentEventBase {
  type: "turn_start";
}

export interface AgentEventTurnEnd extends AgentEventBase {
  type: "turn_end";
  message: unknown;
  tool_results: unknown[];
}

export interface AgentEventMessageStart extends AgentEventBase {
  type: "message_start";
  message: {
    role: string;
    content: unknown;
    [key: string]: unknown;
  };
}

export interface AgentEventMessageUpdate extends AgentEventBase {
  type: "message_update";
  message: {
    role: string;
    content: unknown;
    [key: string]: unknown;
  };
  assistant_message_event: {
    type: string;
    delta?: string | null;
    snapshot?: { role: string; content: unknown };
  };
}

export interface AgentEventMessageEnd extends AgentEventBase {
  type: "message_end";
  message: {
    role: string;
    content: unknown;
    [key: string]: unknown;
  };
}

export interface AgentEventToolStart extends AgentEventBase {
  type: "tool_execution_start";
  tool_call_id: string;
  tool_name: string;
  args: unknown;
}

export interface AgentEventToolUpdate extends AgentEventBase {
  type: "tool_execution_update";
  tool_call_id: string;
  tool_name: string;
  args: unknown;
  partial_result: unknown;
}

export interface AgentEventToolEnd extends AgentEventBase {
  type: "tool_execution_end";
  tool_call_id: string;
  tool_name: string;
  result: unknown;
  is_error: boolean;
}

export interface ContextUsageEvent extends AgentEventBase {
  type: "context_usage";
  tokens: number;
  contextWindow: number;
  percent: number;
}

export interface ErrorEvent extends AgentEventBase {
  type: "error";
  message: string;
}

export type AgentEvent =
  | AgentEventAgentStart
  | AgentEventAgentEnd
  | AgentEventTurnStart
  | AgentEventTurnEnd
  | AgentEventMessageStart
  | AgentEventMessageUpdate
  | AgentEventMessageEnd
  | AgentEventToolStart
  | AgentEventToolUpdate
  | AgentEventToolEnd
  | ContextUsageEvent
  | ErrorEvent;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  thinking?: string;
  toolCalls?: ToolCallEntry[];
  timestamp: number;
  entry_id?: string;
}

export interface ToolCallEntry {
  id: string;
  name: string;
  args: unknown;
  result?: unknown;
  isError: boolean;
  status: "running" | "completed";
}

export interface SessionInfo {
  session_id: string;
  cwd: string;
  model: string;
  message_count?: number;
  is_streaming?: boolean;
  updated_at?: number;
  label?: string;
  entry_count?: number;
}

export interface SessionTreeNode {
  entry: {
    id: string;
    type: string;
    timestamp: number;
    parent_id: string | null;
  };
  children: SessionTreeNode[];
  label: string | null;
}
