const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('trafficLightAPI', {
  // 获取初始配置
  getConfig: () => ipcRenderer.invoke('get-config'),

  // 更新状态到主进程
  updateState: (updates) => ipcRenderer.send('update-state', updates),

  // 调整主窗口尺寸
  adjustWindow: (width, height) => ipcRenderer.send('adjust-window', { width, height }),

  // 切换窗口置顶
  setTopmost: (topmost) => ipcRenderer.send('set-topmost', topmost),

  // 退出应用
  quit: () => ipcRenderer.send('quit-app'),

  // 切换设置面板
  toggleSettings: () => ipcRenderer.send('toggle-settings'),

  // 关闭设置面板
  closeSettings: () => ipcRenderer.send('close-settings'),

  // 打开关于窗口
  openAbout: () => ipcRenderer.send('open-about'),

  // 监听外部 API 状态变化
  onStatusChange: (callback) => {
    ipcRenderer.on('set-status', (event, data) => callback(data));
  },

  // 监听设置面板关闭
  onSettingsClosed: (callback) => {
    ipcRenderer.on('settings-closed', () => callback());
  },

  // 监听状态更新（来自设置面板的变更）
  onStateUpdate: (callback) => {
    ipcRenderer.on('state-update', (event, data) => callback(data));
  },

  // 获取当前状态（设置窗口用）
  getState: () => ipcRenderer.invoke('get-state'),
});
