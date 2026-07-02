import { create } from "zustand";

interface UIState {
  sidebarOpen: boolean;
  settingsOpen: boolean;
  theme: "dark" | "light";
  toggleSidebar: () => void;
  setSidebarOpen: (v: boolean) => void;
  setSettingsOpen: (v: boolean) => void;
  setTheme: (t: "dark" | "light") => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  settingsOpen: false,
  theme: "light",
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  setSettingsOpen: (v) => set({ settingsOpen: v }),
  setTheme: (t) => set({ theme: t }),
}));
