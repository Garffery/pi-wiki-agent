import { useEffect, useState } from "react";
import { AppShell } from "./components/layout/AppShell";
import { Sidebar } from "./components/layout/Sidebar";
import { Header } from "./components/layout/Header";
import { Footer } from "./components/layout/Footer";
import { ChatArea } from "./components/chat/ChatArea";
import { ChatInput } from "./components/input/ChatInput";
import { SettingsPanel } from "./components/settings/SettingsPanel";
import { SessionSwitcher } from "./components/sessions/SessionSwitcher";
import { ErrorBoundary } from "./components/shared/ErrorBoundary";
import { useSessionStore } from "./stores/sessionStore";
import { useChatStore } from "./stores/chatStore";
import { useUIStore } from "./stores/uiStore";
import { useWebSocket } from "./hooks/useWebSocket";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { api } from "./services/api";

function App() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const addSession = useSessionStore((s) => s.addSession);
  const addMessage = useChatStore((s) => s.addMessage);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const setContextUsage = useChatStore((s) => s.setContextUsage);
  const theme = useUIStore((s) => s.theme);
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  // Connect WebSocket when active session changes
  useWebSocket(activeSessionId);

  // Initialize: create or restore session
  useEffect(() => {
    const init = async () => {
      try {
        const sessions = await api.listSessions();
        if (sessions.length > 0) {
          useSessionStore.getState().setSessions(sessions);
          setActiveSession(sessions[0].session_id);
        } else {
          const info = await api.createSession();
          addSession(info);
        }
      } catch (e) {
        console.error("Failed to initialize session:", e);
      }
    };
    init();
  }, []);

  // Poll context usage
  useEffect(() => {
    if (!activeSessionId) return;
    const interval = setInterval(async () => {
      try {
        const usage = await api.getContextUsage(activeSessionId);
        setContextUsage(usage);
      } catch {
        // Ignore
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [activeSessionId, setContextUsage]);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    "Ctrl+K": () => {
      setSwitcherOpen(true);
    },
    "Ctrl+L": () => {
      clearMessages();
    },
    "Ctrl+P": async () => {
      if (!activeSessionId) return;
      try {
        await api.cycleModel(activeSessionId);
        addMessage({
          id: `sys-${Date.now()}`,
          role: "system",
          content: "Switched to next model.",
          timestamp: Date.now(),
        });
      } catch {
        // Ignore
      }
    },
  });

  return (
    <ErrorBoundary>
      <div className={`h-full ${theme === "dark" ? "dark" : ""}`}>
        <AppShell
          sidebar={<Sidebar />}
          header={<Header />}
          footer={<Footer />}
          input={<ChatInput />}
        >
          {settingsOpen ? <SettingsPanel /> : <ChatArea />}
        </AppShell>
        <SessionSwitcher open={switcherOpen} onClose={() => setSwitcherOpen(false)} />
      </div>
    </ErrorBoundary>
  );
}

export default App;
