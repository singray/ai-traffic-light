import pyautogui, time, requests
import json

out_dir = r'C:\Users\18202\WorkBuddy\2026-05-27-14-44-01\traffic-light\screenshots'
api = 'http://localhost:9527/api/status'

# Traffic light window area
LEFT, TOP, W, H = 4472, 1300, 179, 408

def api_set(color):
    try:
        requests.post(api, json={'color': color}, timeout=3)
    except:
        pass

def snap(name, extra_w=0, extra_h=0, extra_x=0, extra_y=0):
    region = (LEFT + extra_x, TOP + extra_y, W + extra_w, H + extra_h)
    img = pyautogui.screenshot(region=region)
    path = out_dir + '\\' + name
    img.save(path)
    print('OK: %s (%dx%d)' % (name, img.width, img.height))

# 1. Green (default)
snap('01-green.png')
time.sleep(0.5)

# 2. Red
api_set('red')
time.sleep(0.8)
snap('02-red.png')
time.sleep(0.5)

# 3. Yellow
api_set('yellow')
time.sleep(0.8)
snap('03-yellow.png')
time.sleep(0.5)

# 4. Restore green
api_set('green')
time.sleep(0.5)

print('Screenshots done!')
