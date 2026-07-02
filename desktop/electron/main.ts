import { app, BrowserWindow, Tray, Menu, nativeImage } from "electron";
import * as path from "path";
import { BackendManager } from "./backend-manager";

const isDev = process.env.NODE_ENV === "development" || process.argv.includes("--dev");

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backend: BackendManager | null = null;
let isQuitting = false;

async function createWindow(backendPort: number): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: "Pi Desktop",
    backgroundColor: "#1a1a2e",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    const url = `http://localhost:5173?backendPort=${backendPort}`;
    await mainWindow.loadURL(url);
    mainWindow.webContents.openDevTools();
  } else {
    const indexPath = path.join(__dirname, "..", "frontend", "dist", "index.html");
    await mainWindow.loadFile(indexPath, {
      query: { backendPort: String(backendPort) },
    });
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createTray(): void {
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip("Pi Desktop");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Show",
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: "separator" },
    {
      label: "Quit",
      click: async () => {
        await cleanup();
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

async function cleanup(): Promise<void> {
  if (backend) {
    await backend.stop();
    backend = null;
  }
}

app.on("ready", async () => {
  try {
    backend = new BackendManager();
    const port = await backend.start();
    await createWindow(port);
    createTray();

    mainWindow?.on("close", (event) => {
      if (!isQuitting) {
        event.preventDefault();
        mainWindow?.hide();
      }
    });
  } catch (err) {
    console.error("Failed to start application:", err);
    app.quit();
  }
});

app.on("before-quit", async () => {
  isQuitting = true;
  await cleanup();
});

app.on("window-all-closed", () => {
  // Don't quit — stay in tray
});

app.on("activate", () => {
  if (mainWindow) {
    mainWindow.show();
  }
});
