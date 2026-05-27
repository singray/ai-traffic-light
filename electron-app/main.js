const { app, BrowserWindow, ipcMain, screen } = require('electron');
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
let apiServer = null;

// 命令行参数
const args = process.argv.slice(2);
const PORT = parseInt(args.find(a => a.startsWith('--port='))?.split('=')[1] || '9527');
const SCALE = parseFloat(args.find(a => a.startsWith('--scale='))?.split('=')[1] || '2.5');
const THEME = args.find(a => a.startsWith('--theme='))?.split('=')[1] || 'dark';
state.theme = THEME;

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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile('index.html');
  mainWindow.setVisibleOnAllWorkspaces(true);

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
  // 如果已打开则关闭（切换行为）
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    closeSettings();
    return;
  }

  if (!mainWindow || mainWindow.isDestroyed()) return;

  const mainBounds = mainWindow.getBounds();

  // 默认弹出在红绿灯左侧
  let settingsX = mainBounds.x - 268;
  let settingsY = mainBounds.y - 8;

  // 左侧空间不够则弹到右侧
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  settingsWindow.loadFile('settings.html');

  // 窗口准备好后再显示（防止闪烁）
  settingsWindow.once('ready-to-show', () => {
    if (settingsWindow && !settingsWindow.isDestroyed()) {
      settingsWindow.show();
      settingsWindow.focus();
    }
  });

  // 失去焦点时自动关闭
  settingsWindow.on('blur', () => {
    // 延迟一小段时间，避免切换焦点时的竞态
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
  // 通知主窗口设置已关闭
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
          const text = color === 'red' ? 'THINKING' : color === 'yellow' ? 'WAITING' : 'DONE';
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
  // 广播给所有窗口（主窗口 + 设置面板）
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('state-update', updates);
  }
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.webContents.send('state-update', updates);
  }
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
  // 设置窗口也跟随
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.setAlwaysOnTop(topmost);
  }
});

ipcMain.on('quit-app', () => {
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
});

app.on('window-all-closed', () => {
  if (apiServer) apiServer.close();
  app.quit();
});

app.on('before-quit', () => {
  if (apiServer) apiServer.close();
});
