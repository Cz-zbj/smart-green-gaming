"""
adb_controller.py

This is the lowest-level module of the automation pipeline: it handles all
communication with the Android emulator/device, including taking screenshots,
tapping, and swiping.

Prerequisites:
1. Android SDK Platform-Tools must be installed, and the `adb` command must
   work directly from the terminal.
   (Test with: `adb --version` in your terminal — if it prints a version
   number, you're good to go.)
2. The emulator (or a real device) must be running, and `adb devices` should
   show it as connected.

Notes:
- This script only handles the "hands" part of the pipeline — executing
  actions and taking screenshots.
- The "eyes and brain" part (having an LLM analyze the screenshot and decide
  the next action) will be implemented in a separate script later.
- First get this "hands" part working (confirm you can screenshot, tap, and
  swipe), then move on to connecting it with the LLM part.
"""

import subprocess
import time
import os


class AdbController:
    def __init__(self, device_id: str = None, screenshot_dir: str = "screenshots"):
        """
        device_id: If multiple devices/emulators are connected to your
                   computer, you need to specify which one to target
                   (use `adb devices` to see the device IDs).
                   If only one device is connected, this can be left as None.
        screenshot_dir: Local folder where screenshots will be saved.
        """
        self.device_id = device_id
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def _adb_prefix(self):
        """
        Internal helper: builds the prefix for adb commands.
        If a device_id was specified, we need to use `adb -s <device_id> ...`,
        otherwise adb will throw an error when multiple devices are connected
        (it won't know which one to target).
        """
        if self.device_id:
            return ["adb", "-s", self.device_id]
        return ["adb"]

    def check_connection(self) -> bool:
        """
        Checks whether a device is connected. Returns True/False.
        This should be called once at the start of any automation run, to
        confirm the environment is set up correctly before doing anything else.
        """
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True
        )
        print("Currently connected devices:")
        print(result.stdout)
        # The output of `adb devices` looks roughly like:
        # List of devices attached
        # emulator-5554   device
        # So as long as there's at least one non-empty line after the header,
        # a device is connected.
        lines = [l for l in result.stdout.strip().split("\n")[1:] if l.strip()]
        return len(lines) > 0

    def take_screenshot(self, filename: str = None) -> str:
        """
        Takes a screenshot and saves it to the local screenshot folder.
        Returns the local file path.

        How it works:
        1. Tell the device/emulator to save a screenshot to its internal
           /sdcard/ directory.
        2. Use `adb pull` to copy that screenshot file to the local computer.
        (This is the classic, most reliable way to take screenshots via adb.)
        """
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        device_path = "/sdcard/screenshot_temp.png"
        local_path = os.path.join(self.screenshot_dir, filename)

        # Step 1: take the screenshot on the device
        subprocess.run(
            self._adb_prefix() + ["shell", "screencap", "-p", device_path],
            check=True,
        )

        # Step 2: pull the screenshot file to the local machine
        subprocess.run(
            self._adb_prefix() + ["pull", device_path, local_path],
            check=True,
        )

        print(f"Screenshot saved to: {local_path}")
        return local_path

    def tap(self, x: int, y: int):
        """
        Simulates tapping the screen at coordinates (x, y).

        Coordinate system:
        - Origin (0, 0) is the top-left corner of the screen.
        - x increases to the right, y increases downward.
        - Exact values depend on the screenshot's pixel dimensions
          (e.g. if the screenshot is 1280x2856, the center of the screen
          is roughly x=640, y=1428).
        """
        print(f"Tapping at: ({x}, {y})")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "tap", str(x), str(y)],
            check=True,
        )

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """
        Simulates a swipe from (x1, y1) to (x2, y2).

        duration_ms: how long the swipe takes, in milliseconds.
        - For games like Flow Free (drag-to-connect puzzles), it's better to
          use a longer duration (e.g. 500-800ms) so the motion resembles a
          human dragging finger, and the game correctly registers it as a
          "draw a line" gesture instead of a quick flick.
        """
        print(f"Swiping: ({x1}, {y1}) -> ({x2}, {y2}), duration {duration_ms}ms")
        subprocess.run(
            self._adb_prefix()
            + [
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            ],
            check=True,
        )

    def swipe_path(self, waypoints, steps_per_segment: int = 6, step_delay: float = 0.025):
        """
        Performs ONE continuous drag through a list of (x, y) waypoints
        WITHOUT lifting the finger in between - this is what real human
        "draw an L-shaped / zig-zag line" gestures look like.

        Why this exists: `swipe()` above only supports a straight line
        between two points, so a multi-segment path (e.g. "go left one
        cell, then down one cell") has to be done as several separate
        `swipe()` calls, each of which lifts the finger at the end of one
        segment and puts it back down to start the next. Games like Flow
        Free sometimes fail to recognize that second touch-down as "keep
        drawing this same line" (especially for short 1-cell segments),
        which silently breaks the connection.

        `swipe_path()` avoids that entirely by sending one continuous
        DOWN -> MOVE -> MOVE -> ... -> UP sequence, interpolating several
        MOVE events between each pair of waypoints so the drag looks
        smooth rather than teleporting.

        waypoints: list of (x, y) pixel tuples, e.g. [(576,1259), (363,1259), (363,1472)]
                   for "start here, go left, then go down".

        Requires Android's `input motionevent` subcommand (available on
        API 31 / Android 12 and up - both your Pixel 6 API34 and
        Pixel 10 Pro API37.1 emulators support it).
        """
        if len(waypoints) < 2:
            raise ValueError("swipe_path needs at least 2 waypoints")

        prefix = self._adb_prefix()

        x0, y0 = waypoints[0]
        print(f"swipe_path: DOWN at ({x0}, {y0})")
        subprocess.run(
            prefix + ["shell", "input", "motionevent", "DOWN", str(x0), str(y0)],
            check=True,
        )
        time.sleep(0.05)

        for (x1, y1), (x2, y2) in zip(waypoints, waypoints[1:]):
            for step in range(1, steps_per_segment + 1):
                t = step / steps_per_segment
                xi = round(x1 + (x2 - x1) * t)
                yi = round(y1 + (y2 - y1) * t)
                subprocess.run(
                    prefix + ["shell", "input", "motionevent", "MOVE", str(xi), str(yi)],
                    check=True,
                )
                time.sleep(step_delay)

        time.sleep(0.05)
        xe, ye = waypoints[-1]
        subprocess.run(
            prefix + ["shell", "input", "motionevent", "UP", str(xe), str(ye)],
            check=True,
        )
        print(f"swipe_path: UP at ({xe}, {ye})")

    def wake_screen(self):
        """Wakes the device if its screen has gone to sleep.

        Needed because the script pauses on an input() prompt waiting for
        you to confirm a result, and the emulator will happily blank its
        screen while it waits. Once that happens the next tap only wakes
        the display and never reaches the button underneath - which is
        exactly why tapping 'next level' worked on Level 1 (no pause
        before it) but silently did nothing on Level 2.
        """
        print("Waking the screen in case it went to sleep...")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            check=True,
        )
        time.sleep(0.8)

    def press_back(self):
        """Presses the system BACK button.

        Useful for dismissing things that shouldn't be there - the share
        sheet, an interstitial ad, a system dialog. If a stray touch lands
        on Flow Free's 'share' button (which sits at roughly y=1805, only
        ~70px above ROW[5]=1875, so any drag along the bottom row will
        sweep across it while a dialog is up), this is how to get back to
        the game.
        """
        print("Pressing BACK to dismiss any overlay...")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "keyevent", "KEYCODE_BACK"],
            check=True,
        )
        time.sleep(1.0)

    def dialog_is_showing(self, probe_xy=(640, 2474)) -> bool:
        """Checks whether the 'Perfect!' dialog is currently on screen.

        Why this is needed: the dialog does NOT always appear. On a level
        that's already been completed before, finishing it again (without
        beating your best) just swaps the bottom bar's centre button from
        the hint bulb to a '->' arrow, with no dialog at all. If the
        script blindly taps the dialog's 'next level' position when no
        dialog is there, that tap lands on the BOARD instead - and
        (640, 1400) happens to be cell (3,3), so on level 8 it tapped
        yellow's endpoint and wiped the line out (5/5 dropped back to
        4/5).

        The probe point is the centre of the bottom bar, which sits below
        the board so it's never a game cell:
          - yellow-ish hint bulb  -> dialog is up
          - white '->' arrow      -> no dialog, level is complete
        """
        path = self.take_screenshot("dialog_probe.png")
        try:
            from PIL import Image
        except ImportError:
            print("Pillow isn't installed (pip install pillow) - can't "
                  "check for the dialog, assuming it's showing.")
            return True

        with Image.open(path) as im:
            r, g, b = im.convert("RGB").getpixel(probe_xy)
        print(f"Probe pixel at {probe_xy}: R={r} G={g} B={b}")

        # The arrow is white (all three channels high); the bulb is yellow
        # (red and green high, blue low).
        arrow_visible = r > 180 and g > 180 and b > 180
        return not arrow_visible

    def go_to_next_level(self, dialog_button, arrow_button=(640, 2474)):
        """Advances to the next level, whichever way the game offers."""
        if self.dialog_is_showing():
            print("Dialog is up - tapping 'next level' inside it.")
            self.tap(*dialog_button)
        else:
            print("No dialog - tapping the '->' arrow in the bottom bar.")
            self.tap(*arrow_button)

    def close_app(self, package_name: str):
        """Force-stops an app, ending the run cleanly."""
        print(f"Closing app: {package_name}")
        subprocess.run(
            self._adb_prefix() + ["shell", "am", "force-stop", package_name],
            check=True,
        )

    def open_app(self, package_name: str):
        """
        Launches an app by its package name (e.g. Flow Free).

        How to find the package_name:
        1. Open the app manually on the device.
        2. Run this in your terminal: adb shell dumpsys window | grep mCurrentFocus
        3. The output will show something like com.bigduckgames.flow/...
           — the first part (com.bigduckgames.flow) is the package_name.
        """
        print(f"Attempting to open app: {package_name}")
        subprocess.run(
            self._adb_prefix()
            + ["shell", "monkey", "-p", package_name, "-c",
               "android.intent.category.LAUNCHER", "1"],
            check=True,
        )


# Package name for Flow Free, found earlier using:
#   adb shell pm list packages | findstr flow
FLOW_FREE_PACKAGE = "com.bigduckgames.flow"


if __name__ == "__main__":
    controller = AdbController(screenshot_dir="screenshots_FlowFree")

    print("=== Step 1: Checking device connection ===")
    if not controller.check_connection():
        print("No device detected! Make sure the emulator is running and "
              "adb is configured correctly.")
        exit(1)

    print("\n=== Step 2: Opening Flow Free automatically ===")
    controller.open_app(FLOW_FREE_PACKAGE)

    # Give the app a moment to actually launch and render before we take
    # a screenshot - if we screenshot too fast, we might just capture a
    # blank/loading screen instead of the actual game.
    # (Bumped from 3s to 8s - sometimes the free play screen takes longer
    # to finish loading, especially on a cold start.)
    print("Waiting a few seconds for the app to fully load...")
    time.sleep(8)

    print("\n=== Step 3: Taking a screenshot to confirm the game opened ===")
    screenshot_path = controller.take_screenshot("flow_free_opened.png")
    print(f"Please open {screenshot_path} to confirm Flow Free actually opened")

    # Coordinates found by hovering the mouse over "free play" in the
    # screenshot using Paint (image is 1280x2856 pixels). This row appears
    # to be a full-width tappable button (it has a ">" arrow on the right),
    # so exact x doesn't matter much - the y-coordinate (the row's height)
    # is what matters most.
    print("\n=== Step 4: Tapping 'free play' ===")
    print("Waiting an extra 1.5 seconds to make sure the menu has fully rendered...")
    time.sleep(1.5)
    controller.tap(640, 1281)

    print("Waiting a few seconds for the menu transition...")
    time.sleep(2)

    print("\n=== Step 5: Taking a screenshot to confirm we entered free play ===")
    screenshot_path = controller.take_screenshot("flow_free_play_menu.png")
    print(f"Please open {screenshot_path} to confirm we're in the free play menu")

    print("\n=== Step 6: Tapping 'Classic Pack' ===")
    controller.tap(350, 862)

    print("Waiting a few seconds for the level list to load...")
    time.sleep(2)

    print("\n=== Step 7: Taking a screenshot to confirm we entered Classic Pack ===")
    screenshot_path = controller.take_screenshot("flow_free_classic_pack.png")
    print(f"Please open {screenshot_path} to confirm we're in the Classic Pack level list")

    print("\n=== Step 8: Tapping 'Level 1' ===")
    controller.tap(281, 978)

    print("Waiting a few seconds for the level to load...")
    time.sleep(2)

    print("\n=== Step 9: Taking a screenshot to confirm we entered Level 1 ===")
    screenshot_path = controller.take_screenshot("flow_free_level1.png")
    print(f"Please open {screenshot_path} to confirm we're inside Level 1")

    print("\n=== Step 10: Solving Level 1 (5x5) automatically ===")
    # Grid coordinate mapping, calibrated from measured pixel positions.
    #
    # These were re-measured after blue kept failing to reach the bottom
    # row. The original numbers had been read off a Paint window that was
    # displaying the screenshot at 90% zoom, so EVERY coordinate came out
    # 0.9x too small. Near the top-left that's only a ~15px error (which
    # is why yellow, green and red worked fine for so long), but the error
    # compounds toward the bottom-right: the old ROW[5]=1685 was ~190px
    # off, and since a cell is only 234px tall, that put it in row 4
    # rather than row 5 - so blue could never drop into the bottom row.
    #
    # Anchored on two directly measured cell centres:
    #   (col4, row5) = (883, 1873)   (col5, row5) = (1117, 1878)
    # giving a cell pitch of 234px in both axes.
    COL = {1: 181, 2: 415, 3: 649, 4: 883, 5: 1117}
    ROW = {1: 939, 2: 1173, 3: 1407, 4: 1641, 5: 1875}

    def cell(col, row):
        """Helper: converts a (col, row) grid position into (x, y) pixels."""
        return COL[col], ROW[row]

    # Puzzle solution (worked out manually by analyzing the screenshot):
    #   Red:    (1,1) -> straight down to (1,5) -> right to (2,5)
    #   Green:  (3,1) -> left to (2,1) -> straight down to (2,4)
    #   Yellow: (5,1) -> left to (4,1) -> straight down to (4,4)
    #   Blue:   (3,2) -> straight down to (3,5)
    #   Orange: (5,2) -> straight down to (5,5) -> left to (4,5)
    # (using (col,row) notation to match the grid analysis above)

    print("Drawing RED line...")
    controller.swipe(*cell(1, 1), *cell(1, 5), duration_ms=700)
    time.sleep(0.3)
    controller.swipe(*cell(1, 5), *cell(2, 5), duration_ms=400)
    time.sleep(1.0)

    print("Drawing GREEN line...")
    controller.swipe(*cell(3, 1), *cell(2, 1), duration_ms=400)
    time.sleep(0.3)
    controller.swipe(*cell(2, 1), *cell(2, 4), duration_ms=700)
    time.sleep(1.0)

    print("Drawing BLUE line...")
    controller.swipe(*cell(3, 2), *cell(3, 5), duration_ms=700)
    time.sleep(1.0)

    print("Drawing YELLOW line...")
    controller.swipe(*cell(5, 1), *cell(4, 1), duration_ms=400)
    time.sleep(0.3)
    controller.swipe(*cell(4, 1), *cell(4, 4), duration_ms=700)
    time.sleep(1.0)

    print("Drawing ORANGE line...")
    controller.swipe(*cell(5, 2), *cell(5, 5), duration_ms=700)
    time.sleep(0.3)
    controller.swipe(*cell(5, 5), *cell(4, 5), duration_ms=400)
    time.sleep(1.0)

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 11: Taking a final screenshot to check the result ===")
    screenshot_path = controller.take_screenshot("flow_free_level1_result.png")
    print(f"Please open {screenshot_path} to see if the level was solved correctly")

    # Centre of the "next level" button in the "Perfect!" dialog.
    # Shared by every level.
    #
    # WATCH OUT: the dialog has two layouts and the button moves between
    # them. With 3 buttons (next level / remove ads / share) it spans
    # roughly y 1291-1452, so 1400 sits comfortably inside. With only 2
    # buttons (next level / share) it spans roughly 1395-1558, so 1400 is
    # barely 5px past the top edge - see the level 6 result screenshot.
    # If that tap misses, the dialog stays up and the NEXT level's drawing
    # swipes land on it instead of the board.
    NEXT_LEVEL_BUTTON = (640, 1400)

    print("\n=== Step 12: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 13: Taking a screenshot of Level 2 ===")
    screenshot_path = controller.take_screenshot("flow_free_level2.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 2")

    print("\n=== Step 14: Solving Level 2 (5x5) automatically ===")
    # Endpoint layout read off the flow_free_level2.png screenshot
    # (using the SAME (col,row) grid mapping as Level 1, since it's the
    # same 5x5 board size/position):
    #   Yellow: (1,1) <-> (5,4)
    #   Green:  (3,3) <-> (2,4)
    #   Red:    (3,4) <-> (1,5)
    #   Blue:   (1,4) <-> (5,5)
    #
    # Solution below fills the entire 25-cell board with no overlaps and
    # without cutting through another color's endpoint dot:
    #   Yellow: (1,1) -> right across row 1 -> (5,1) -> down -> (5,4)
    #   Green:  (3,3) -> left -> (2,3) -> down -> (2,4)
    #   Red:    (3,4) -> down -> (3,5) -> left across row 5 -> (1,5)
    #   Blue:   (1,4) -> up -> (1,2) -> right -> (4,2) -> down -> (4,5)
    #           -> right -> (5,5)
    #
    # Touch registration on the emulator is a bit flaky (a lift-and-redown
    # between segments occasionally doesn't get read as "continue this
    # line"), so instead of hardcoding one giant fragile sequence, each
    # color's path is stored as a list of (col,row) waypoints and drawn by
    # a shared helper. That way, if a color fails to connect, we can just
    # redraw THAT ONE color afterward instead of re-running everything.
    LEVEL2_PATHS = {
        "yellow": [(1, 1), (5, 1), (5, 4)],
        "green":  [(3, 3), (2, 3), (2, 4)],
        "red":    [(3, 4), (3, 5), (1, 5)],
        "blue":   [(1, 4), (1, 2), (4, 2), (4, 5), (5, 5)],
    }

    def expand_to_cells(waypoints):
        """Expands a list of corner waypoints into EVERY cell along the
        way, e.g. [(1,4),(1,2)] -> [(1,4),(1,3),(1,2)].

        Why: a multi-cell swipe sometimes falls short (blue's (1,4)->(1,2)
        drag stopped at (1,3) once), and because every following segment
        starts where the previous one ended, one short segment silently
        kills the entire rest of the line - in Flow Free, starting a drag
        on an empty cell does nothing at all. Moving one cell at a time
        keeps each drag as short as possible and means every drag starts
        from a cell that's already part of the line."""
        cells = [waypoints[0]]
        for (c1, r1), (c2, r2) in zip(waypoints, waypoints[1:]):
            step_c = (c2 > c1) - (c2 < c1)   # -1, 0 or +1
            step_r = (r2 > r1) - (r2 < r1)
            c, r = c1, r1
            while (c, r) != (c2, r2):
                c += step_c
                r += step_r
                cells.append((c, r))
        return cells

    def draw_path(waypoints, duration_ms=500, between_cell_sleep=0.5,
                  after_color_sleep=1.5):
        """Draws a line one cell at a time along the expanded path.

        On duration_ms: since every drag is only one cell, the swipe has
        to be SLOW, not fast - a short distance covered in a short time
        gets classified as a tap rather than a drag, and a tap on the head
        of a line does nothing in Flow Free.

        NOTE: two things were tried here and removed. One continuous
        finger-down drag via `input motionevent DOWN/MOVE/UP` doesn't work
        because each event has to be sent as its own separate `adb shell`
        process, so Android doesn't treat them as the same touch and the
        drag goes off-course. Overshooting past each cell centre to force
        entry also backfired - it made every landing off-centre and the
        errors compounded, sending yellow through the wrong row. Aim at
        cell centres, and make sure those centres are measured correctly.
        """
        cells = [cell(c, r) for c, r in expand_to_cells(waypoints)]
        for (x1, y1), (x2, y2) in zip(cells, cells[1:]):
            controller.swipe(x1, y1, x2, y2, duration_ms=duration_ms)
            time.sleep(between_cell_sleep)
        time.sleep(after_color_sleep)

    # DRAW ORDER MATTERS - green goes LAST, on purpose.
    #
    # Green's endpoints (3,3) and (2,4) are only 3 cells apart, but when
    # it was drawn early the game kept auto-routing it the long way round
    # through (3,2) and (2,2) in row 2 - and blue's path runs straight
    # across row 2, so blue would then overwrite those cells and break
    # green. (That U-shaped green is also unsolvable: it leaves blue with
    # a dead end at (1,2), so the board can never fill to 100%.)
    #
    # By drawing yellow, red and blue FIRST, the only cells still free by
    # the time green is drawn are exactly (2,3) and (2,4) - so green
    # physically cannot detour anywhere else, and nothing gets drawn
    # afterwards that could overwrite it.
    DRAW_ORDER = ["yellow", "red", "blue", "green"]

    for color_name in DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL2_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 15: Taking a screenshot to check Level 2 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level2_result.png")
    print(f"Please open {screenshot_path} to see if Level 2 was solved correctly")

    print("\n=== Step 16: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 17: Taking a screenshot of Level 3 ===")
    screenshot_path = controller.take_screenshot("flow_free_level3.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 3")

    print("\n=== Step 18: Solving Level 3 (5x5, 5 flows) automatically ===")
    # Endpoint layout read off flow_free_level3.png:
    #   Yellow: (2,1) <-> (1,4)
    #   Blue:   (3,1) <-> (1,5)
    #   Green:  (4,1) <-> (4,5)
    #   Red:    (4,2) <-> (3,3)
    #   Orange: (4,4) <-> (3,5)
    #
    # Column 5 contains no endpoints at all, so some line has to detour
    # into it to fill the board. Green is the natural candidate: it runs
    # right from (4,1) into column 5, straight down to (5,5), then back
    # left onto its own endpoint at (4,5), swallowing the whole column.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  Y Y B G G
    #   row2:  Y B B R G
    #   row3:  Y B R R G
    #   row4:  Y B O O G
    #   row5:  B B O G G
    LEVEL3_PATHS = {
        "green":  [(4, 1), (5, 1), (5, 5), (4, 5)],
        "yellow": [(2, 1), (1, 1), (1, 4)],
        "blue":   [(3, 1), (3, 2), (2, 2), (2, 5), (1, 5)],
        "red":    [(4, 2), (4, 3), (3, 3)],
        "orange": [(4, 4), (3, 4), (3, 5)],
    }

    # Same trick as Level 2: the long structural lines go first, and the
    # short 3-cell ones (red, orange) go last. By then every other cell is
    # taken, so they have exactly one route available and can't be
    # auto-routed off on a detour.
    LEVEL3_DRAW_ORDER = ["green", "yellow", "blue", "red", "orange"]

    for color_name in LEVEL3_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL3_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 19: Taking a screenshot to check Level 3 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level3_result.png")
    print(f"Please open {screenshot_path} to see if Level 3 was solved correctly")

    print("\n=== Step 20: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 21: Taking a screenshot of Level 4 ===")
    screenshot_path = controller.take_screenshot("flow_free_level4.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 4")

    print("\n=== Step 22: Solving Level 4 (5x5, 4 flows) automatically ===")
    # Endpoint layout read off flow_free_level4.png:
    #   Red:    (4,1) <-> (1,2)
    #   Green:  (5,1) <-> (1,5)
    #   Yellow: (3,3) <-> (3,5)
    #   Blue:   (4,4) <-> (2,5)
    #
    # The bottom row is the constraint: green's (1,5) has blue's (2,5) and
    # yellow's (3,5) immediately to its right, so green can't approach
    # along row 5 - it has to drop into (1,5) from (1,4) above. That
    # forces green into a long S-shape down the right side, back across
    # row 2, and down column 1.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  R R R R G
    #   row2:  R G G G G
    #   row3:  G G Y Y Y
    #   row4:  G B B B Y
    #   row5:  G B Y Y Y
    LEVEL4_PATHS = {
        "green":  [(5, 1), (5, 2), (2, 2), (2, 3), (1, 3), (1, 5)],
        "yellow": [(3, 3), (5, 3), (5, 5), (3, 5)],
        "red":    [(4, 1), (1, 1), (1, 2)],
        "blue":   [(4, 4), (2, 4), (2, 5)],
    }

    # Blue is the shortest line and goes last: by then the only free cells
    # left are exactly the four it needs, so it has no room to wander.
    LEVEL4_DRAW_ORDER = ["green", "yellow", "red", "blue"]

    for color_name in LEVEL4_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL4_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 23: Taking a screenshot to check Level 4 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level4_result.png")
    print(f"Please open {screenshot_path} to see if Level 4 was solved correctly")

    print("\n=== Step 24: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 25: Taking a screenshot of Level 5 ===")
    screenshot_path = controller.take_screenshot("flow_free_level5.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 5")

    print("\n=== Step 26: Solving Level 5 (5x5, 4 flows) automatically ===")
    # Endpoint layout read off flow_free_level5.png:
    #   Red:    (4,1) <-> (3,5)
    #   Green:  (5,1) <-> (4,2)
    #   Yellow: (2,2) <-> (5,5)
    #   Blue:   (3,2) <-> (5,4)
    #
    # Green's two endpoints are almost touching - it only needs 3 cells -
    # so the other 22 cells fall to red, yellow and blue. Red does the
    # heavy lifting: left along row 1, then all the way down column 1 and
    # back along row 5, wrapping the whole left and bottom edge.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  R R R R G
    #   row2:  R Y B G G
    #   row3:  R Y B B B
    #   row4:  R Y Y Y B
    #   row5:  R R R Y Y
    LEVEL5_PATHS = {
        "red":    [(4, 1), (1, 1), (1, 5), (3, 5)],
        "yellow": [(2, 2), (2, 4), (4, 4), (4, 5), (5, 5)],
        "blue":   [(3, 2), (3, 3), (5, 3), (5, 4)],
        "green":  [(5, 1), (5, 2), (4, 2)],
    }

    # Green is only 3 cells long, so it goes last - by then its three
    # cells are the only ones left free and it can't be routed anywhere
    # else.
    LEVEL5_DRAW_ORDER = ["red", "yellow", "blue", "green"]

    for color_name in LEVEL5_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL5_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 27: Taking a screenshot to check Level 5 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level5_result.png")
    print(f"Please open {screenshot_path} to see if Level 5 was solved correctly")

    print("\n=== Step 28: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 29: Taking a screenshot of Level 6 ===")
    screenshot_path = controller.take_screenshot("flow_free_level6.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 6")

    print("\n=== Step 30: Solving Level 6 (5x5, 4 flows) automatically ===")
    # Endpoint layout read off flow_free_level6.png:
    #   Yellow: (1,1) <-> (5,5)
    #   Blue:   (3,1) <-> (2,4)
    #   Red:    (4,1) <-> (5,4)
    #   Green:  (5,1) <-> (4,3)
    #
    # Cell (2,1) pins the whole solution down: its only neighbours are
    # (1,1), (3,1) and (2,2), and (1,1) is yellow's endpoint. So (2,1)
    # can only belong to blue - blue has to step LEFT out of (3,1) first,
    # then run down column 2. Yellow takes the left edge down and the
    # entire bottom row across.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  Y B B R G
    #   row2:  Y B R R G
    #   row3:  Y B R G G
    #   row4:  Y B R R R
    #   row5:  Y Y Y Y Y
    LEVEL6_PATHS = {
        "yellow": [(1, 1), (1, 5), (5, 5)],
        "red":    [(4, 1), (4, 2), (3, 2), (3, 4), (5, 4)],
        "blue":   [(3, 1), (2, 1), (2, 4)],
        "green":  [(5, 1), (5, 3), (4, 3)],
    }

    # Green (4 cells) is the shortest, so it goes last and has exactly one
    # possible route by the time it's drawn.
    LEVEL6_DRAW_ORDER = ["yellow", "red", "blue", "green"]

    for color_name in LEVEL6_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL6_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 31: Taking a screenshot to check Level 6 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level6_result.png")
    print(f"Please open {screenshot_path} to see if Level 6 was solved correctly")

    print("\n=== Step 32: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 33: Taking a screenshot of Level 7 ===")
    # If this shows level 6's dialog still sitting there rather than a
    # fresh level 7 board, the tap above missed - and everything that goes
    # wrong on level 7 follows from that, because level 7's yellow line
    # sweeps right across the bottom of the screen where 'share' lives.
    screenshot_path = controller.take_screenshot("flow_free_level7.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 7")

    print("\n=== Step 34: Solving Level 7 (5x5, 4 flows) automatically ===")
    # Endpoint layout read off flow_free_level7.png:
    #   Blue:   (1,1) <-> (4,3)
    #   Yellow: (4,1) <-> (1,3)
    #   Green:  (1,2) <-> (3,3)
    #   Red:    (2,4) <-> (4,4)
    #
    # Neither row 5 nor column 5 contains a single endpoint, so one line
    # has to swallow both. Yellow is the one that can: right from (4,1)
    # into column 5, down to (5,5), back across the whole bottom row to
    # (1,5), then up to its endpoint at (1,3) - wrapping the entire right
    # and bottom edge in one stroke.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  B B B Y Y
    #   row2:  G G B B Y
    #   row3:  Y G G B Y
    #   row4:  Y R R R Y
    #   row5:  Y Y Y Y Y
    LEVEL7_PATHS = {
        "yellow": [(4, 1), (5, 1), (5, 5), (1, 5), (1, 3)],
        "blue":   [(1, 1), (3, 1), (3, 2), (4, 2), (4, 3)],
        "green":  [(1, 2), (2, 2), (2, 3), (3, 3)],
        "red":    [(2, 4), (4, 4)],
    }

    # DRAW ORDER: yellow goes LAST here, and that's about where the finger
    # lifts, not about routing.
    #
    # The level completes the instant the final cell is filled, which
    # happens while the finger is still DOWN mid-swipe. The "Perfect!"
    # dialog pops up immediately, and the swipe's UP event then lands on
    # whatever the dialog put at that position.
    #
    # With red last, the completing drag ended at (4,4) = (883, 1641). In
    # the 2-button dialog layout the 'share' button covers y 1596-1760 -
    # so the release tapped 'share' and threw the run out to the Android
    # share sheet. (Confirmed: the after-green screenshot is a clean
    # board with no dialog; the after-red one is the share sheet.)
    #
    # Yellow ends at (1,3) = (181, 1407). The dialog's buttons only span
    # x 211-1070, so x=181 lands on dialog background - a dead area that
    # swallows the release harmlessly. Yellow's route is still forced:
    # by the time it's drawn, its 12 cells are the only free ones left.
    LEVEL7_DRAW_ORDER = ["blue", "green", "red", "yellow"]

    # Screenshot after EVERY colour on this level, to pin down exactly
    # when the share sheet appears. The level 7 result screenshot showed
    # the share sheet sitting over the home screen - taken BEFORE the
    # 'next level' tap - so something during the drawing is opening it,
    # not the tap. These per-colour shots will show which stroke does it.
    for color_name in LEVEL7_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL7_PATHS[color_name])
        controller.take_screenshot(f"level7_after_{color_name}.png")

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 35: Taking a screenshot to check Level 7 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level7_result.png")
    print(f"Please open {screenshot_path} to see if Level 7 was solved correctly")

    print("\n=== Step 36: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 37: Taking a screenshot of Level 8 ===")
    screenshot_path = controller.take_screenshot("flow_free_level8.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 8")

    print("\n=== Step 38: Solving Level 8 (5x5, 5 flows) automatically ===")
    # Endpoint layout read off flow_free_level8.png:
    #   Blue:   (1,1) <-> (2,5)
    #   Red:    (4,1) <-> (2,4)
    #   Orange: (5,1) <-> (3,4)
    #   Yellow: (4,2) <-> (3,3)
    #   Green:  (5,4) <-> (3,5)
    #
    # Column 1 is completely empty apart from blue's (1,1), and nothing
    # else can reach it, so blue runs the full left edge down and hooks
    # right into (2,5). Red pulls left out of (4,1) and takes column 2.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  B R R R O
    #   row2:  B R Y Y O
    #   row3:  B R Y O O
    #   row4:  B R O O G
    #   row5:  B B G G G
    LEVEL8_PATHS = {
        "blue":   [(1, 1), (1, 5), (2, 5)],
        "red":    [(4, 1), (2, 1), (2, 4)],
        "orange": [(5, 1), (5, 3), (4, 3), (4, 4), (3, 4)],
        "yellow": [(4, 2), (3, 2), (3, 3)],
        "green":  [(5, 4), (5, 5), (3, 5)],
    }

    # Green goes last for the same reason yellow does on level 7: the
    # board completes mid-swipe while the finger is still down, so the
    # release lands on the freshly-drawn dialog. Green ends at (3,5) =
    # (649, 1875), which is below the dialog's bottom edge (~1840), so
    # there's no button there to hit. Ending on orange (3,4) or red (2,4)
    # would put the release at y=1641 - right on 'share'.
    LEVEL8_DRAW_ORDER = ["blue", "red", "orange", "yellow", "green"]

    for color_name in LEVEL8_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL8_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 39: Taking a screenshot to check Level 8 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level8_result.png")
    print(f"Please open {screenshot_path} to see if Level 8 was solved correctly")

    print("\n=== Step 40: Tapping 'next level' ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 41: Taking a screenshot of Level 9 ===")
    screenshot_path = controller.take_screenshot("flow_free_level9.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 9")

    print("\n=== Step 42: Solving Level 9 (5x5, 4 flows) automatically ===")
    # Endpoint layout read off flow_free_level9.png:
    #   Red:    (4,1) <-> (3,5)
    #   Yellow: (2,2) <-> (3,3)
    #   Blue:   (3,2) <-> (1,5)
    #   Green:  (4,2) <-> (2,5)
    #
    # Column 5 is empty, so red turns right out of (4,1), runs the whole
    # column down to (5,5) and comes back left to its endpoint. Blue goes
    # the other way: up out of (3,2), left along row 1, then down the
    # entire first column.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  B B B R R
    #   row2:  B Y B G R
    #   row3:  B Y Y G R
    #   row4:  B G G G R
    #   row5:  B G R R R
    #
    # Yellow is written BACKWARDS here, ending on (2,2) rather than
    # (3,3). It's the last line drawn, so its final release happens just
    # as the dialog appears - and (3,3) is (649, 1407), right on top of
    # 'next level'. (2,2) is (415, 1173), which lands in the dialog's
    # message text where there's nothing to press.
    LEVEL9_PATHS = {
        "red":    [(4, 1), (5, 1), (5, 5), (3, 5)],
        "blue":   [(3, 2), (3, 1), (1, 1), (1, 5)],
        "green":  [(4, 2), (4, 4), (2, 4), (2, 5)],
        "yellow": [(3, 3), (2, 3), (2, 2)],
    }

    LEVEL9_DRAW_ORDER = ["red", "blue", "green", "yellow"]

    for color_name in LEVEL9_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL9_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 43: Taking a screenshot to check Level 9 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level9_result.png")
    print(f"Please open {screenshot_path} to see if Level 9 was solved correctly")

    print("\n=== Step 44: Moving on to the next level ===")
    controller.go_to_next_level(NEXT_LEVEL_BUTTON)

    print("Waiting a few seconds for the next level to load...")
    time.sleep(2)

    print("\n=== Step 45: Taking a screenshot of Level 10 ===")
    screenshot_path = controller.take_screenshot("flow_free_level10.png")
    print(f"Please open {screenshot_path} to confirm we're now in Level 10")

    print("\n=== Step 46: Solving Level 10 (5x5, 4 flows) automatically ===")
    # Endpoint layout read off flow_free_level10.png:
    #   Green:  (1,2) <-> (5,5)
    #   Red:    (4,2) <-> (2,3)
    #   Blue:   (1,3) <-> (3,3)
    #   Yellow: (4,3) <-> (1,5)
    #
    # Blue's two endpoints sit on the same row with a single cell between
    # them - but that cell, (2,3), is red's endpoint, so blue can't go
    # straight across and has to loop down through row 4. Green wraps the
    # whole top row and the whole right column.
    #
    # Final tiling - all 25 cells used exactly once:
    #   row1:  G G G G G
    #   row2:  G R R R G
    #   row3:  B R B Y G
    #   row4:  B B B Y G
    #   row5:  Y Y Y Y G
    #
    # Yellow finishes the board, ending on (1,5) = (181, 1875) - outside
    # the dialog's buttons both horizontally and vertically, so the
    # release as the dialog pops up can't press anything.
    LEVEL10_PATHS = {
        "green":  [(1, 2), (1, 1), (5, 1), (5, 5)],
        "red":    [(4, 2), (2, 2), (2, 3)],
        "blue":   [(1, 3), (1, 4), (3, 4), (3, 3)],
        "yellow": [(4, 3), (4, 5), (1, 5)],
    }

    LEVEL10_DRAW_ORDER = ["green", "red", "blue", "yellow"]

    for color_name in LEVEL10_DRAW_ORDER:
        print(f"Drawing {color_name.upper()} line...")
        draw_path(LEVEL10_PATHS[color_name])

    print("Waiting a moment for the completion animation...")
    time.sleep(2)

    print("\n=== Step 47: Taking a screenshot to check Level 10 result ===")
    screenshot_path = controller.take_screenshot("flow_free_level10_result.png")
    print(f"Please open {screenshot_path} to see if Level 10 was solved correctly")

    print("\n=== Step 48: Closing the game - run finished ===")
    controller.close_app(FLOW_FREE_PACKAGE)
    print("All 10 levels done. Flow Free has been closed.")