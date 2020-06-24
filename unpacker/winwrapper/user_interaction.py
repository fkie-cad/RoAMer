import time
import random

import logging
from ctypes import windll


class UserInteractor:

    def __init__(self):
        self.startX = 67
        self.startY = 120
        self.currentX = 0
        self.currentY = 0
        self.spoofMinX = 100
        self.spoofMaxX = 300
        self.spoofMinY = 5
        self.spoofMaxY = 100

    # based on https://github.com/cuckoosandbox/cuckoo/blob/master/cuckoo/data/analyzer/windows/modules/auxiliary/human.py
    def move_mouse(self, x, y):
        # Move mouse to top-middle position.
        windll.user32.SetCursorPos(x, y)
        self.currentX = x
        self.currentY = y

    def click_mouse(self, x, y):
        # Mouse down.
        logging.info("Clicking mouse @(%d, %d)", x, y)
        windll.user32.mouse_event(2, 0, 0, 0, None)
        time.sleep(0.01)
        # Mouse up.
        windll.user32.mouse_event(4, 0, 0, 0, None)

    def launch_sample(self, x, y):
        self.press_f5()
        time.sleep(1.5)
        self.mouse_double_click(x, y)

    def mouse_double_click(self, x, y):
        self.move_mouse(x, y)
        self.click_mouse(x, y)
        self.click_mouse(x, y)

    def press_f5(self):
        windll.user32.keybd_event(116, 0x45, 1 | 0, 0)
        windll.user32.keybd_event(116, 0x45, 1 | 2, 0)

    def move_mouse_randomly(self):
        nextPosX = random.randrange(self.spoofMinX, self.spoofMaxX)
        nextPosY = random.randrange(self.spoofMinY, self.spoofMaxY)
        for i in range(20):
            diffX = abs(self.currentX - nextPosX) // 2
            diffX = -1 * diffX if self.currentX > nextPosX else diffX
            diffY = abs(self.currentY - nextPosY) // 2
            diffY = -1 * diffY if self.currentY > nextPosY else diffY
            self.move_mouse(self.currentX + diffX, self.currentY + diffY)
            time.sleep(0.001)
        self.move_mouse(nextPosX, nextPosY)

    def type_in_notepad(self):
        self.mouse_double_click(self.startX, self.startY)
        time.sleep(0.1)

    def simulate_user_interaction(self, seconds):
        if seconds > 0.5:
            self.type_in_notepad()
            pass
        start = time.time()
        while True:
            self.move_mouse_randomly()
            currentTime = time.time()
            if currentTime - start >= seconds:
                break
        return
