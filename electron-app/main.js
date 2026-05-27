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
let aboutWindow = null;
let tray = null;
let apiServer = null;
// 防抖：程序打开子窗口时，主窗口会获得焦点，需要忽略短时间内的 focus 事件
let ignoreFocusUntil = 0;

// 命令行参数
const args = process.argv.slice(2);
const PORT = parseInt(args.find(a => a.startsWith('--port='))?.split('=')[1] || '9527');
const SCALE = parseFloat(args.find(a => a.startsWith('--scale='))?.split('=')[1] || '2.5');
const THEME = args.find(a => a.startsWith('--theme='))?.split('=')[1] || 'dark';
state.theme = THEME;

// ============================================================
// 托盘图标 - 内嵌生成，避免外部 ICO 格式问题
// ============================================================
function createTrayIcon() {
  const W = 16, H = 16;
  const buf = Buffer.alloc(W * H * 4, 0); // BGRA, bottom-up

  function setPixel(x, y, r, g, b, a) {
    if (x < 0 || x >= W || y < 0 || y >= H) return;
    const row = H - 1 - y;
    const idx = (row * W + x) * 4;
    buf[idx] = b;
    buf[idx + 1] = g;
    buf[idx + 2] = r;
    buf[idx + 3] = a;
  }

  function fillCircle(cx, cy, radius, r, g, b, a) {
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const dx = x - cx, dy = y - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist <= radius) {
          const aa = dist > radius - 0.8 ? Math.max(0, (radius - dist) / 0.8) : 1;
          setPixel(x, y, r, g, b, Math.round(a * aa));
        }
      }
    }
  }

  function fillRect(rx, ry, rw, rh, r, g, b, a) {
    for (let y = ry; y < ry + rh; y++) {
      for (let x = rx; x < rx + rw; x++) {
        setPixel(x, y, r, g, b, a);
      }
    }
  }

  // 深色圆角背景
  fillRect(2, 1, 12, 14, 40, 40, 42, 255);
  // 圆角修正
  setPixel(2, 1, 0, 0, 0, 0);
  setPixel(13, 1, 0, 0, 0, 0);
  setPixel(2, 14, 0, 0, 0, 0);
  setPixel(13, 14, 0, 0, 0, 0);

  // 红灯
  fillCircle(8, 5, 2.2, 255, 59, 48, 255);
  // 黄灯
  fillCircle(8, 9, 2.2, 255, 204, 0, 255);
  // 绿灯
  fillCircle(8, 13, 2.2, 48, 209, 88, 255);

  return nativeImage.createFromBitmap(buf, { width: W, height: H });
}

let trayIcon = null;

function getIcon() {
  if (!trayIcon) {
    trayIcon = createTrayIcon();
  }
  return trayIcon;
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
    skipTaskbar: true,
    icon: getIcon(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile('index.html');
  mainWindow.setVisibleOnAllWorkspaces(true);

  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('focus', () => {
    // 程序打开子窗口时忽略 focus 事件（防抖 500ms）
    if (Date.now() < ignoreFocusUntil) return;
    closeSettings();
    closeAbout();
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

  // 防抖：阻止主窗口 focus 事件误杀即将打开的子窗口
  ignoreFocusUntil = Date.now() + 500;

  if (!mainWindow.isVisible()) {
    mainWindow.show();
  }

  closeAbout();

  const mainBounds = mainWindow.getBounds();
  let settingsX = mainBounds.x - 268;
  let settingsY = mainBounds.y - 8;

  if (settingsX < 0) {
    settingsX = mainBounds.x + mainBounds.width + 12;
  }

  settingsWindow = new BrowserWindow({
    width: 260,
    height: 250,
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
      if (Date.now() < ignoreFocusUntil) return;
      if (settingsWindow && !settingsWindow.isDestroyed()) {
        closeSettings();
      }
    }, 200);
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
// 关于窗口
// ============================================================
function openAbout() {
  if (aboutWindow && !aboutWindow.isDestroyed()) {
    closeAbout();
    return;
  }

  if (!mainWindow || mainWindow.isDestroyed()) return;

  // 防抖：关闭设置时主窗口会获得焦点，阻止 focus 事件误杀 about 窗口
  ignoreFocusUntil = Date.now() + 500;

  closeSettings();

  const mainBounds = mainWindow.getBounds();
  let aboutX = mainBounds.x - 228;
  let aboutY = mainBounds.y + mainBounds.height - 160;

  if (aboutX < 0) {
    aboutX = mainBounds.x + mainBounds.width + 12;
  }
  if (aboutY < 0) aboutY = 10;

  aboutWindow = new BrowserWindow({
    width: 220,
    height: 160,
    x: aboutX,
    y: aboutY,
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

  aboutWindow.loadFile('about.html');

  aboutWindow.once('ready-to-show', () => {
    if (aboutWindow && !aboutWindow.isDestroyed()) {
      aboutWindow.show();
      aboutWindow.focus();
    }
  });

  aboutWindow.on('blur', () => {
    setTimeout(() => {
      if (Date.now() < ignoreFocusUntil) return;
      if (aboutWindow && !aboutWindow.isDestroyed()) {
        closeAbout();
      }
    }, 200);
  });

  aboutWindow.on('closed', () => {
    aboutWindow = null;
  });
}

function closeAbout() {
  if (aboutWindow && !aboutWindow.isDestroyed()) {
    aboutWindow.destroy();
    aboutWindow = null;
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
  if (aboutWindow && !aboutWindow.isDestroyed()) {
    aboutWindow.setAlwaysOnTop(topmost);
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

ipcMain.on('open-about', () => {
  openAbout();
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
