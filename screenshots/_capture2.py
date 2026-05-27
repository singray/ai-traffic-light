import pyautogui, time

out_dir = r'C:\Users\18202\WorkBuddy\2026-05-27-14-44-01\traffic-light\screenshots'

# Traffic light window area
LEFT, TOP, W, H = 4472, 1300, 179, 408

def snap(name, extra_w=300, extra_h=0, extra_x=-300, extra_y=0):
    """Capture with extra space for settings panel on the left"""
    region = (LEFT + extra_x, TOP + extra_y, W + extra_w, H + extra_h)
    img = pyautogui.screenshot(region=region)
    path = out_dir + '\\' + name
    img.save(path)
    print('OK: %s (%dx%d)' % (name, img.width, img.height))

# Right-click on the traffic light to open settings panel
# Click in the middle of the traffic light
click_x = LEFT + W // 2
click_y = TOP + H // 2
print('Right-clicking at (%d, %d) to open settings...' % (click_x, click_y))
pyautogui.click(click_x, click_y, button='right')
time.sleep(0.6)

# Take screenshot with settings panel visible
snap('04-settings.png', extra_w=320, extra_x=-320)
time.sleep(0.3)

# Now click on the traffic light area to close settings
pyautogui.click(LEFT + 20, TOP + H - 20)
time.sleep(0.5)

print('Done!')
