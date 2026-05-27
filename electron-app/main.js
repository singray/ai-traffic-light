const { app, BrowserWindow, ipcMain, screen, Tray, Menu, nativeImage } = require('electron');
const http = require('http');
const path = require('path');

// ============================================================
// 状态管理
// ============================================================
let state = {
  color: 'green',
  theme: 'dark',
  singleLight: false,
  alwaysOnTop: true,
};

let mainWindow = null;
let settingsWindow = null;
let tray = null;
let apiServer = null;

// 命令行参数
const args = process.argv.slice(2);
const PORT = parseInt(args.find(a => a.startsWith('--port='))?.split('=')[1] || '9527');
const SCALE = parseFloat(args.find(a => a.startsWith('--scale='))?.split('=')[1] || '2.5');
const THEME = args.find(a => a.startsWith('--theme='))?.split('=')[1] || 'dark';
state.theme = THEME;

// ============================================================
// 图标
// ============================================================
const iconPath = path.join(__dirname, 'assets', 'icon.ico');

function getIcon() {
  return nativeImage.createFromPath(iconPath);
}

// ============================================================
// 系统托盘
// ============================================================
function createTray() {
  tray = new Tray(getIcon());
  tray.setToolTip('AI Traffic Light');
  updateTrayMenu();

  // 单击托盘图标 → 显示/隐藏主窗口
  tray.on('click', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });
}

function updateTrayMenu() {
  const colorLabel = state.color === 'red' ? '🔴 正在思考' : state.color === 'yellow' ? '🟡 等待确认' : '🟢 已完成';
  const contextMenu = Menu.buildFromTemplate([
    { label: colorLabel, enabled: false },
    { type: 'separator' },
    { label: '🔴 红灯 - 正在思考', type: 'radio', checked: state.color === 'red', click: () => setState('red') },
    { label: '🟡 黄灯 - 等待确认', type: 'radio', checked: state.color === 'yellow', click: () => setState('yellow') },
    { label: '🟢 绿灯 - 已完成', type: 'radio', checked: state.color === 'green', click: () => setState('green') },
    { type: 'separator' },
    { label: '设置...', click: () => openSettings() },
    { type: 'separator' },
    { label: '退出', click: () => { if (apiServer) apiServer.close(); app.quit(); } },
  ]);
  if (tray) {
    tray.setContextMenu(contextMenu);
  }
}

function setState(color) {
  state.color = color;
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('set-status', { color });
  }
  updateTrayMenu();
  // 更新托盘图标提示
  const text = color === 'red' ? '正在思考' : color === 'yellow' ? '等待确认' : '已完成';
  if (tray) tray.setToolTip('AI Traffic Light - ' + text);
}

// ============================================================
// 创建主窗口（只有红绿灯）
// ============================================================
function createWindow() {
  const { width: screenW } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: 120,
    height: 200,
    x: screenW - 150,
    y: 80,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    hasShadow: false,
    skipTaskbar: true,  // 主窗口不占任务栏，用托盘代替
    icon: getIcon(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile('index.html');
  mainWindow.setVisibleOnAllWorkspaces(true);

  // 关闭窗口时隐藏而非退出（托盘模式）
  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  // 主窗口获得焦点时关闭设置面板
  mainWindow.on('focus', () => {
    closeSettings();
  });

  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

// ============================================================
// 设置面板窗口（独立弹出）
// ============================================================
function openSettings() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    closeSettings();
    return;
  }

  if (!mainWindow || mainWindow.isDestroyed()) return;

  // 确保主窗口可见
  if (!mainWindow.isVisible()) {
    mainWindow.show();
  }

  const mainBounds = mainWindow.getBounds();

  let settingsX = mainBounds.x - 268;
  let settingsY = mainBounds.y - 8;

  if (settingsX < 0) {
    settingsX = mainBounds.x + mainBounds.width + 12;
  }

  settingsWindow = new BrowserWindow({
    width: 260,
    height: 210,
    x: settingsX,
    y: settingsY,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    hasShadow: false,
    skipTaskbar: true,
    focusable: true,
    show: false,
    icon: getIcon(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  settingsWindow.loadFile('settings.html');

  settingsWindow.once('ready-to-show', () => {
    if (settingsWindow && !settingsWindow.isDestroyed()) {
      settingsWindow.show();
      settingsWindow.focus();
    }
  });

  settingsWindow.on('blur', () => {
    setTimeout(() => {
      if (settingsWindow && !settingsWindow.isDestroyed()) {
        closeSettings();
      }
    }, 150);
  });

  settingsWindow.on('closed', () => {
    settingsWindow = null;
  });
}

function closeSettings() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.destroy();
    settingsWindow = null;
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('settings-closed');
  }
}

// ============================================================
// HTTP API 服务
// ============================================================
function startApiServer() {
  apiServer = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    if (req.method === 'GET' && req.url === '/api/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'running', port: PORT }));
      return;
    }

    if (req.method === 'GET' && req.url === '/api/status') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'ok',
        color: state.color,
        text: state.color === 'red' ? 'THINKING' : state.color === 'yellow' ? 'WAITING' : 'DONE',
        theme: state.theme,
        singleLight: state.singleLight,
        alwaysOnTop: state.alwaysOnTop,
      }));
      return;
    }

    if (req.method === 'POST' && req.url === '/api/status') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          const data = JSON.parse(body || '{}');
          const color = (data.color || '').toLowerCase();
          if (!['red', 'yellow', 'green'].includes(color)) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Invalid color: [red, yellow, green]' }));
            return;
          }
          state.color = color;
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('set-status', { color });
          }
          // 同步托盘状态
          updateTrayMenu();
          const text = color === 'red' ? 'THINKING' : color === 'yellow' ? 'WAITING' : 'DONE';
          if (tray) tray.setToolTip('AI Traffic Light - ' + text);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'ok', color, text }));
        } catch {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    res.writeHead(404);
    res.end('Not Found');
  });

  apiServer.listen(PORT, '127.0.0.1', () => {
    console.log(`[TrafficLight] API Server: http://127.0.0.1:${PORT}`);
  });
}

// ============================================================
// IPC 通信
// ============================================================
ipcMain.handle('get-config', () => ({
  scale: SCALE,
  theme: state.theme,
  port: PORT,
}));

ipcMain.handle('get-state', () => ({ ...state }));

ipcMain.on('update-state', (event, updates) => {
  Object.assign(state, updates);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('state-update', updates);
  }
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.webContents.send('state-update', updates);
  }
  // 状态变更时更新托盘
  if ('color' in updates) updateTrayMenu();
});

ipcMain.on('adjust-window', (event, { width, height }) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    const [x, y] = mainWindow.getPosition();
    mainWindow.setBounds({ x, y, width, height });
  }
});

ipcMain.on('set-topmost', (event, topmost) => {
  state.alwaysOnTop = topmost;
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setAlwaysOnTop(topmost);
  }
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.setAlwaysOnTop(topmost);
  }
});

ipcMain.on('quit-app', () => {
  app.isQuitting = true;
  if (apiServer) apiServer.close();
  app.quit();
});

ipcMain.on('toggle-settings', () => {
  openSettings();
});

ipcMain.on('close-settings', () => {
  closeSettings();
});

// ============================================================
// 应用生命周期
// ============================================================
app.whenReady().then(() => {
  startApiServer();
  createWindow();
  createTray();
});

app.on('window-all-closed', () => {
  // 托盘模式下不退出，用户通过托盘退出
});

app.on('before-quit', () => {
  app.isQuitting = true;
  if (apiServer) apiServer.close();
});

app.on('activate', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
  }
});
