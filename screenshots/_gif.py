import pyautogui, time, requests
from PIL import Image

out_dir = r'C:\Users\18202\WorkBuddy\2026-05-27-14-44-01\traffic-light\screenshots'
api = 'http://localhost:9527/api/status'
LEFT, TOP, W, H = 4472, 1300, 179, 408

def api_set(color):
    try:
        requests.post(api, json={'color': color}, timeout=3)
    except:
        pass

frames = []

# Start with green
api_set('green')
time.sleep(0.5)

# Capture green
region = (LEFT, TOP, W, H)
for _ in range(5):
    frames.append(pyautogui.screenshot(region=region))
    time.sleep(0.15)

# Switch to red
api_set('red')
for _ in range(8):
    frames.append(pyautogui.screenshot(region=region))
    time.sleep(0.3)

# Switch to yellow
api_set('yellow')
for _ in range(6):
    frames.append(pyautogui.screenshot(region=region))
    time.sleep(0.2)

# Switch back to green
api_set('green')
for _ in range(6):
    frames.append(pyautogui.screenshot(region=region))
    time.sleep(0.2)

# Save as GIF (30fps)
gif_path = out_dir + '\\demo.gif'
frames[0].save(
    gif_path,
    save_all=True,
    append_images=frames[1:],
    duration=150,
    loop=0,
    optimize=False,
)
print('GIF saved: %s (%d frames, %dx%d)' % (gif_path, len(frames), frames[0].width, frames[0].height))
