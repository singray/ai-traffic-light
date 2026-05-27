import pyautogui, time

out_dir = r'C:\Users\18202\WorkBuddy\2026-05-27-14-44-01\traffic-light\screenshots'

# Traffic light window area
LEFT, TOP, W, H = 4472, 1300, 179, 408

# Settings panel: 260x250, left of traffic light
# settingsX = LEFT - 268 = 4204, settingsY = TOP - 8 = 1292
SETTINGS_X = LEFT - 268
SETTINGS_Y = TOP - 8
SETTINGS_W = 260
SETTINGS_H = 250

def snap(name, extra_w=300, extra_h=0, extra_x=-300, extra_y=0):
    region = (LEFT + extra_x, TOP + extra_y, W + extra_w, H + extra_h)
    img = pyautogui.screenshot(region=region)
    path = out_dir + '\\' + name
    img.save(path)
    print('OK: %s (%dx%d)' % (name, img.width, img.height))

# Right-click on the traffic light to open settings
click_x = LEFT + W // 2
click_y = TOP + H // 2
pyautogui.click(click_x, click_y, button='right')
time.sleep(0.7)

# The settings panel should be visible now.
# "关于" button is near the bottom of the settings panel
about_x = SETTINGS_X + SETTINGS_W // 2
about_y = SETTINGS_Y + SETTINGS_H - 30
print('Clicking about button at (%d, %d)' % (about_x, about_y))
pyautogui.click(about_x, about_y)
time.sleep(0.7)

# Now the about window should be visible
# About window: 220x160, positioned near settings/traffic light area
# Capture a wider area to include both
snap('05-about.png', extra_w=320, extra_x=-320)
time.sleep(0.3)

# Click away to close
pyautogui.click(LEFT + 20, TOP + H - 20)
time.sleep(0.3)

print('Done!')
