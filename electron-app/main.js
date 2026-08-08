const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const BACKEND_PORT = 8899;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

let backendProcess = null;
let mainWindow = null;

// ── Backend process management ─────────────────────────────────────────

function getBackendCommand() {
  if (app.isPackaged) {
    const backendExe = path.join(process.resourcesPath, 'backend', 'backend.exe');
    return { cmd: backendExe, args: [], cwd: path.dirname(backendExe) };
  } else {
    const projectRoot = path.join(__dirname, '..');
    return { cmd: 'uv', args: ['run', 'pi-wiki-desktop'], cwd: projectRoot };
  }
}

function startBackend() {
  const { cmd, args, cwd } = getBackendCommand();
  const isWindows = process.platform === 'win32';

  backendProcess = spawn(cmd, args, {
    cwd,
    shell: isWindows,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.on('error', (err) => {
    console.error('[backend] Failed to start:', err.message);
  });

  backendProcess.on('exit', (code) => {
    console.log(`[backend] Process exited with code ${code}`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (!backendProcess) return;
  console.log('[backend] Stopping...');

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', backendProcess.pid, '/f', '/t'], { shell: true });
  } else {
    backendProcess.kill('SIGTERM');
  }
  backendProcess = null;
}

// ── Health check polling ───────────────────────────────────────────────

function waitForBackend(maxRetries = 60, interval = 500) {
  return new Promise((resolve, reject) => {
    let retries = 0;

    const check = () => {
      const req = http.get(`${BACKEND_URL}/api/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      });

      req.on('error', () => retry());
      req.setTimeout(1000, () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      retries++;
      if (retries >= maxRetries) {
        reject(new Error(`Backend did not respond on ${BACKEND_URL} after ${maxRetries} attempts`));
      } else {
        setTimeout(check, interval);
      }
    };

    check();
  });
}

// ── Window ─────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'Wiki 管理',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(BACKEND_URL);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── App lifecycle ──────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend();

  try {
    await waitForBackend();
    createWindow();
  } catch (err) {
    console.error(err.message);
    dialog.showErrorBox('启动失败', `后端服务无法启动。\n\n${err.message}`);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  stopBackend();
  app.quit();
});

app.on('before-quit', () => {
  stopBackend();
});

app.on('will-quit', () => {
  stopBackend();
});
