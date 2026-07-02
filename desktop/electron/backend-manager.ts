import { ChildProcess, spawn } from "child_process";
import * as path from "path";
import * as http from "http";

const isDev = process.env.NODE_ENV === "development" || process.argv.includes("--dev");

export class BackendManager {
  private process: ChildProcess | null = null;
  private port: number = 0;

  async start(): Promise<number> {
    const backendPath = this.getBackendPath();
    console.log(`Starting backend: ${backendPath}`);

    const args = isDev ? ["run", "python", "-m", "pi_desktop_backend.main"] : [];
    const cmd = isDev ? "uv" : backendPath;

    return new Promise((resolve, reject) => {
      const proc = spawn(cmd, args, {
        env: { ...process.env, PI_DESKTOP_PORT: "0", PYTHONUNBUFFERED: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });

      this.process = proc;

      let started = false;

      proc.stdout?.on("data", (data: Buffer) => {
        const output = data.toString();
        console.log(`[backend] ${output.trim()}`);

        if (!started) {
          try {
            const parsed = JSON.parse(output.trim());
            if (parsed.port) {
              this.port = parsed.port;
              started = true;
              this.waitForHealth(parsed.port)
                .then(() => resolve(parsed.port))
                .catch(reject);
            }
          } catch {
            // Not JSON yet, keep waiting
          }
        }
      });

      proc.stderr?.on("data", (data: Buffer) => {
        console.error(`[backend:err] ${data.toString().trim()}`);
      });

      proc.on("error", (err) => {
        console.error(`Failed to start backend: ${err.message}`);
        if (!started) reject(err);
      });

      proc.on("exit", (code) => {
        console.log(`Backend exited with code ${code}`);
        if (!started) {
          reject(new Error(`Backend exited with code ${code} before starting`));
        }
      });

      // Timeout after 30s
      setTimeout(() => {
        if (!started) {
          proc.kill();
          reject(new Error("Backend startup timed out"));
        }
      }, 30000);
    });
  }

  async stop(): Promise<void> {
    if (!this.process) return;

    return new Promise((resolve) => {
      const proc = this.process!;

      proc.on("exit", () => {
        console.log("Backend stopped");
        this.process = null;
        resolve();
      });

      // SIGTERM on Windows sends WM_CLOSE, on Unix it's graceful
      if (process.platform === "win32") {
        // On Windows, use taskkill to ensure all child processes die
        spawn("taskkill", ["/F", "/T", "/PID", String(proc.pid)]);
      } else {
        proc.kill("SIGTERM");
      }

      // Force kill after 5s
      setTimeout(() => {
        if (this.process) {
          try {
            proc.kill("SIGKILL");
          } catch {
            // Already dead
          }
        }
        resolve();
      }, 5000);
    });
  }

  getPort(): number {
    return this.port;
  }

  private getBackendPath(): string {
    const resourcesPath = process.resourcesPath || "";
    const backendDir = path.join(resourcesPath, "backend");

    if (process.platform === "win32") {
      return path.join(backendDir, "pi-desktop-backend.exe");
    }
    return path.join(backendDir, "pi-desktop-backend");
  }

  private waitForHealth(port: number): Promise<void> {
    const maxRetries = 30;
    let retries = 0;

    return new Promise((resolve, reject) => {
      const check = () => {
        const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
          if (res.statusCode === 200) {
            resolve();
          } else {
            retry();
          }
        });

        req.on("error", () => retry());
        req.setTimeout(1000, () => {
          req.destroy();
          retry();
        });
      };

      const retry = () => {
        retries++;
        if (retries >= maxRetries) {
          reject(new Error("Backend health check timed out"));
          return;
        }
        setTimeout(check, 1000);
      };

      check();
    });
  }
}
