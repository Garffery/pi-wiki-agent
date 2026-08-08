# Electron 桌面应用打包指南

## 目录结构

```
electron-app/
├── package.json              # Electron + electron-builder 依赖配置
├── electron-builder.yml      # 打包配置（NSIS Windows 安装包）
├── main.js                   # Electron 主进程
├── preload.js                # 预加载脚本
├── assets/icon.ico           # 应用图标
├── scripts/
│   ├── backend_entry.py      # PyInstaller 打包入口
│   ├── build-backend.py      # PyInstaller 构建脚本
│   └── 7za_wrapper.py        # 7za 包装器（处理 Windows 软链接问题）
├── build/
│   ├── dist/backend/         # PyInstaller 输出
│   └── .pyinstaller/         # PyInstaller 临时文件
└── dist/                     # electron-builder 输出
    ├── Wiki 管理 Setup x.x.x.exe      # NSIS 安装包
    └── win-unpacked/                  # 解压即用版
```

## 环境准备

确保已安装：

```bash
# Node.js 依赖
cd electron-app && npm install

# Python 依赖（PyInstaller + Pillow）
uv pip install pyinstaller Pillow
```

## 打包步骤

### 1. 打包 Python 后端

```bash
cd electron-app
npm run build:backend
```

此命令执行 `scripts/build-backend.py`，用 PyInstaller 将 FastAPI 后端 + 所有 Python 依赖 + 前端静态文件打包为 `build/dist/backend/backend.exe`。

### 2. 打包 Windows 安装包

```bash
cd electron-app
npm run build:win
```

此命令先执行 `build:backend`，然后调用 electron-builder 生成 NSIS 安装包。

### 3. 输出

```
electron-app/dist/
├── Wiki 管理 Setup 0.53.0.exe    # 安装包，约 120MB
├── Wiki 管理 Setup 0.53.0.exe.blockmap
└── win-unpacked/                 # 解压即用版（调试用）
```

## 开发调试

```bash
cd electron-app
npm run dev
```

Electron 窗口启动，后端通过 `uv run pi-wiki-desktop` 拉起，支持热重载。

## 常见问题

### 1. Electron 二进制下载失败

国内网络可能无法访问 GitHub，需设置镜像：

```bash
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
export ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/"
```

或直接在 `electron-builder.yml` 中配置：

```yaml
electronDownload:
  mirror: https://npmmirror.com/mirrors/electron/
```

### 2. winCodeSign 解压报错（软链接问题）

winCodeSign 的 7z 包中包含 macOS 软链接（`.dylib`），Windows 非管理员用户解压时会报错。

**解决方案**：已内置 `scripts/7za_wrapper.py` 包装器，构建时自动替换 `7za.exe`。如需手动处理：

```bash
# 1. 重命名原 7za.exe
mv node_modules/7zip-bin/win/x64/7za.exe node_modules/7zip-bin/win/x64/7za_real.exe

# 2. 编译包装器
uv run python -m PyInstaller --onefile --name 7za \
  --distpath node_modules/7zip-bin/win/x64 \
  scripts/7za_wrapper.py

# 3. 清理缓存
rm -rf "$LOCALAPPDATA/electron-builder/Cache/winCodeSign"
```

### 3. PyInstaller 找不到模块

在 `scripts/build-backend.py` 的 `HIDDEN_IMPORTS` 列表中添加缺失的模块名。

### 4. 更新版本号

修改 `electron-app/package.json` 中的 `version` 字段，打包后的安装包文件名会自动更新。

## 工作流程

```
源码修改 → 前端/后端开发完成
    ↓
npm run build:win（一键打包）
    ↓
dist/Wiki 管理 Setup x.x.x.exe
    ↓
发给用户 → 双击安装 → 桌面快捷方式 → 即开即用
```

用户无需安装 Python、Node.js 或任何运行环境。
