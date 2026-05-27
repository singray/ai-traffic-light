const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('trafficLightAPI', {
  // 获取初始配置
  getConfig: () => ipcRenderer.invoke('get-config'),

  // 更新状态到主进程
  updateState: (updates) => ipcRenderer.send('update-state', updates),

  // 调整窗口尺寸
  adjustWindow: (width, height) => ipcRenderer.send('adjust-window', { width, height }),

  // 切换窗口置顶
  setTopmost: (topmost) => ipcRenderer.send('set-topmost', topmost),

  // 退出应用
  quit: () => ipcRenderer.send('quit-app'),

  // 监听来自外部 API 的状态变化
  onStatusChange: (callback) => {
    ipcRenderer.on('set-status', (event, data) => callback(data));
  },
});
