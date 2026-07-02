/** REST API client for backend communication */

const BASE = "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  // Health
  health: () => request<{ status: string }>("/api/health"),

  // Sessions
  createSession: (cwd?: string) =>
    request<{ session_id: string; cwd: string; model: string }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ cwd }),
    }),

  listSessions: () => request<any[]>("/api/sessions"),

  getSession: (id: string) => request<any>(`/api/sessions/${id}`),

  deleteSession: (id: string) =>
    request<any>(`/api/sessions/${id}`, { method: "DELETE" }),

  getMessages: (id: string) =>
    request<{ messages: any[] }>(`/api/sessions/${id}/messages`),

  sendPrompt: (id: string, message: string, images?: any[]) =>
    request<{ status: string }>(`/api/sessions/${id}/prompt`, {
      method: "POST",
      body: JSON.stringify({ message, images }),
    }),

  abort: (id: string) =>
    request<any>(`/api/sessions/${id}/abort`, { method: "POST" }),

  compact: (id: string) =>
    request<any>(`/api/sessions/${id}/compact`, { method: "POST" }),

  executeCommand: (id: string, command: string, args: string = "") =>
    request<any>(`/api/sessions/${id}/command`, {
      method: "POST",
      body: JSON.stringify({ command, args }),
    }),

  forkSession: (id: string, entryId?: string) =>
    request<any>(`/api/sessions/${id}/fork`, {
      method: "POST",
      body: JSON.stringify({ entry_id: entryId }),
    }),

  getSessionTree: (id: string) =>
    request<{ session_id: string; tree: any[] }>(`/api/sessions/${id}/tree`),

  getForkPoints: (id: string) =>
    request<{ session_id: string; fork_points: { entry_id: string; text: string }[] }>(`/api/sessions/${id}/fork-points`),

  // Model & thinking
  setModel: (id: string, provider: string, modelId: string) =>
    request<any>(`/api/sessions/${id}/model`, {
      method: "PUT",
      body: JSON.stringify({ provider, model_id: modelId }),
    }),

  cycleModel: (id: string) =>
    request<any>(`/api/sessions/${id}/model/cycle`, { method: "POST" }),

  setThinking: (id: string, level: string) =>
    request<any>(`/api/sessions/${id}/thinking`, {
      method: "PUT",
      body: JSON.stringify({ level }),
    }),

  cycleThinking: (id: string) =>
    request<any>(`/api/sessions/${id}/thinking/cycle`, { method: "POST" }),

  getTools: (id: string) =>
    request<{ tools: string[] }>(`/api/sessions/${id}/tools`),

  getContextUsage: (id: string) =>
    request<any>(`/api/sessions/${id}/context`),

  // Settings
  getSettings: () => request<any>("/api/settings"),

  updateSettings: (settings: any) =>
    request<any>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
};
