const { app, BrowserWindow, ipcMain, screen } = require('electron');
const http = require('http');
const path = require('path');

// ============================================================
// 状态管理
// ============================================================
let state = {
  color: 'red',
  theme: 'dark',
  singleLight: false,
  alwaysOnTop: true,
};

let mainWindow = null;
let apiServer = null;

// 命令行参数
const args = process.argv.slice(2);
const PORT = parseInt(args.find(a => a.startsWith('--port='))?.split('=')[1] || '9527');
const SCALE = parseFloat(args.find(a => a.startsWith('--scale='))?.split('=')[1] || '2.5');
const THEME = args.find(a => a.startsWith('--theme='))?.split('=')[1] || 'dark';
state.theme = THEME;

// ============================================================
// 创建无边框悬浮窗
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

  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
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

ipcMain.on('update-state', (event, updates) => {
  Object.assign(state, updates);
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
});

ipcMain.on('quit-app', () => {
  if (apiServer) apiServer.close();
  app.quit();
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
