const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('trafficLightAPI', {
  // 获取初始配置
  getConfig: () => ipcRenderer.invoke('get-config'),

  // 更新状态到主进程
  updateState: (updates) => ipcRenderer.send('update-state', updates),

  // 调整主窗口尺寸
  adjustWindow: (width, height) => ipcRenderer.send('adjust-window', { width, height }),

  // 移动主窗口（主进程驱动拖拽，renderer 只发信号）
  // dragStart 必须把 mousedown 时鼠标在窗口内的偏移传过去，
  // 主进程才能用绝对定位算法（cursor - offset = 窗口左上角），
  // 否则因 IPC 异步时差，鼠标与窗口的相对位置会漂移。
  dragStart: (offset) => ipcRenderer.send('drag-start', offset),
  dragMove: () => ipcRenderer.send('drag-move'),
  dragEnd: () => ipcRenderer.send('drag-end'),

  // 鼠标穿透切换：true = 透明区域穿透到下层应用，false = 当前窗口接收事件
  setIgnore: (ignore) => ipcRenderer.send('set-ignore', ignore),

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
