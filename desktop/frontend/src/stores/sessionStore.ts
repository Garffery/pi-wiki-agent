import { create } from "zustand";
import type { SessionInfo } from "../types/events";

interface SessionState {
  sessions: SessionInfo[];
  activeSessionId: string | null;
  loading: boolean;
  searchQuery: string;
  setSessions: (sessions: SessionInfo[]) => void;
  setActiveSession: (id: string) => void;
  addSession: (session: SessionInfo) => void;
  removeSession: (id: string) => void;
  updateSession: (id: string, updates: Partial<SessionInfo>) => void;
  setLoading: (loading: boolean) => void;
  setSearchQuery: (query: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  activeSessionId: null,
  loading: false,
  searchQuery: "",
  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  addSession: (session) =>
    set((s) => ({
      sessions: [...s.sessions, session],
      activeSessionId: s.activeSessionId ?? session.session_id,
    })),
  removeSession: (id) =>
    set((s) => ({
      sessions: s.sessions.filter((sess) => sess.session_id !== id),
      activeSessionId: s.activeSessionId === id ? null : s.activeSessionId,
    })),
  updateSession: (id, updates) =>
    set((s) => ({
      sessions: s.sessions.map((sess) =>
        sess.session_id === id ? { ...sess, ...updates } : sess
      ),
    })),
  setLoading: (loading) => set({ loading }),
  setSearchQuery: (query) => set({ searchQuery: query }),
}));
