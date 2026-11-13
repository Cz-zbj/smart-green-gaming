"""
sky_arena_x1_adb_controller.py

Garen Forest cleared at x1 battle speed, for the energy comparison against
the x2 and x3 variants.

    python sky_arena_x1_adb_controller.py

No arguments. Run it and it runs.

WHY THERE ARE NO ARGUMENTS ANY MORE
------------------------------------
An earlier version took --speed and --current and worked the tap count out as
(target - current) mod 3. It defaulted to 3 and 3, so running it plainly
computed zero taps and never touched the speed button at all - twice, in two
different sessions, and both times the run finished cleanly while measuring
the wrong thing. A script whose default behaviour is to silently do nothing is
worse than no script.

The speed control is a cycle - x1 -> x2 -> x3 -> x1, one step per tap - and a
cold-started game sits at x3. One tap gets to x1. That is a fixed fact about
this experiment, so it is a constant, not a parameter.

For the other speeds, copy this file and change the two constants at the top:

    x1 : SPEED_TAPS = 1     x2 : SPEED_TAPS = 2     x3 : SPEED_TAPS = 0

and re-measure BATTLE_WAIT_BY_STAGE for that speed. The waits are not a fixed
multiple of each other, so scaling one table into another overshoots.

SPEED FIRST, AUTO SECOND
-------------------------
Auto starts the fighting immediately, and once the battle is running the speed
button is buried under combat animation: the tap goes out, adb reports
success, and the speed never changes. With auto still off the battle sits
waiting for input, so the speed button can be tapped at leisure.
"""

import subprocess
import time
import os
import re
import sys
import xml.etree.ElementTree as ET


TAP_MODE = "instant"
TAP_HOLD_MS = 150


class AdbController:
    def __init__(self, device_id: str = None,
                 screenshot_dir: str = "screenshots_sky_arena_x1"):
        self.device_id = device_id
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def _adb_prefix(self):
        if self.device_id:
            return ["adb", "-s", self.device_id]
        return ["adb"]

    def check_connection(self) -> bool:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        print("Currently connected devices:")
        print(result.stdout)
        lines = [l for l in (result.stdout or "").strip().split("\n")[1:] if l.strip()]
        return len(lines) > 0

    def take_screenshot(self, filename: str = None) -> str:
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        device_path = "/sdcard/screenshot_temp.png"
        local_path = os.path.join(self.screenshot_dir, filename)

        subprocess.run(
            self._adb_prefix() + ["shell", "screencap", "-p", device_path],
            check=True,
        )
        subprocess.run(
            self._adb_prefix() + ["pull", device_path, local_path],
            check=True,
        )
        print(f"Screenshot saved to: {local_path}")
        return local_path

    def tap(self, x: int, y: int):
        if TAP_MODE == "held":
            self.tap_held(x, y)
        else:
            self.tap_instant(x, y)

    def tap_instant(self, x: int, y: int):
        print(f"Tapping at: ({x}, {y})")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "touchscreen", "tap", str(x), str(y)],
            check=True,
        )

    def tap_held(self, x: int, y: int, ms: int = None):
        ms = TAP_HOLD_MS if ms is None else ms
        print(f"Tapping at: ({x}, {y}) held {ms}ms")
        subprocess.run(
            self._adb_prefix()
            + ["shell", "input", "touchscreen", "swipe",
               str(x), str(y), str(x), str(y), str(ms)],
            check=True,
        )

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        print(f"Swiping: ({x1}, {y1}) -> ({x2}, {y2})")
        subprocess.run(
            self._adb_prefix()
            + ["shell", "input", "touchscreen", "swipe",
               str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
            check=True,
        )

    def input_text(self, text: str):
        print(f"Typing text: {text!r}")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "text", text],
            check=True,
        )

    def clear_app_data(self, package_name: str):
        """NOT used on this game - wiping it destroys the account and several
        GB of downloaded assets."""
        print(f"Clearing app data for: {package_name}")
        subprocess.run(
            self._adb_prefix() + ["shell", "pm", "clear", package_name],
            check=True,
        )

    def dump_ui(self) -> str:
        subprocess.run(
            self._adb_prefix() + ["shell", "uiautomator", "dump", "/sdcard/ui.xml"],
            capture_output=True, check=True,
        )
        result = subprocess.run(
            self._adb_prefix() + ["shell", "cat", "/sdcard/ui.xml"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        return result.stdout or ""

    def find_text_node(self, text: str):
        xml = self.dump_ui()
        if not xml.strip().startswith("<"):
            print(f"  UI dump didn't return XML: {xml[:120]!r}")
            return None
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            print(f"  couldn't parse UI dump: {exc}")
            return None
        for node in root.iter("node"):
            if node.get("text", "") != text:
                continue
            nums = [int(n) for n in re.findall(r"\d+", node.get("bounds", ""))]
            if len(nums) != 4:
                continue
            x1, y1, x2, y2 = nums
            enabled = node.get("enabled", "true") == "true"
            return ((x1 + x2) // 2, (y1 + y2) // 2), enabled
        return None

    def find_text_center(self, text: str):
        found = self.find_text_node(text)
        return found[0] if found else None

    def tap_text(self, text: str) -> bool:
        pos = self.find_text_center(text)
        if pos is None:
            print(f"  '{text}' not found on screen")
            return False
        print(f"  tapping '{text}' at {pos}")
        self.tap(*pos)
        return True

    def open_app(self, package_name: str):
        print(f"Attempting to open app: {package_name}")
        subprocess.run(
            self._adb_prefix()
            + ["shell", "monkey", "-p", package_name, "-c",
               "android.intent.category.LAUNCHER", "1"],
            check=True,
        )

    def force_stop(self, package_name: str):
        """Cold start guarantees auto-battle is off and the speed is at x3,
        which is what makes the fixed tap counts below correct."""
        print(f"Force-stopping: {package_name}")
        subprocess.run(
            self._adb_prefix() + ["shell", "am", "force-stop", package_name],
            check=True,
        )

    def list_packages(self, keyword: str = None):
        result = subprocess.run(
            self._adb_prefix() + ["shell", "pm", "list", "packages"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        names = [l.replace("package:", "").strip()
                 for l in (result.stdout or "").splitlines() if l.strip()]
        if keyword:
            names = [n for n in names if keyword.lower() in n.lower()]
        for n in sorted(names):
            print("  " + n)
        return names

    def screen_size(self):
        result = subprocess.run(
            self._adb_prefix() + ["shell", "wm", "size"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        out = (result.stdout or "").strip()
        print(out)
        m = re.search(r"(\d+)x(\d+)", out)
        self.nat_w, self.nat_h = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        return self.nat_w, self.nat_h

    def framebuffer_size(self):
        """Real framebuffer, read from the PNG header - bytes 16..24 of any
        PNG are width and height as big-endian uint32.

        MUST be called while the game is on screen. The device is portrait at
        rest and the game rotates the display once it has launched, so
        measuring earlier records 1280x2856 and every fraction resolves to a
        point in the wrong orientation. That failure is silent."""
        path = self.take_screenshot("_size_probe.png")
        with open(path, "rb") as fh:
            head = fh.read(24)
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        os.remove(path)
        self.fb_w, self.fb_h = w, h
        orientation = "landscape" if w > h else "portrait"
        print(f"Framebuffer (screenshot) size: {w} x {h}  ({orientation})")
        return w, h

    def tap_frac(self, fx: float, fy: float):
        if getattr(self, "fb_w", None) is None:
            raise RuntimeError("call framebuffer_size() first")
        if self.fb_w < self.fb_h:
            raise RuntimeError(
                f"framebuffer is {self.fb_w}x{self.fb_h} (portrait) but this "
                "game is landscape - the size was measured before the game "
                "rotated the screen. Re-measure once the game is on screen."
            )
        x = int(round(fx * self.fb_w))
        y = int(round(fy * self.fb_h))
        print(f"  frac ({fx:.3f}, {fy:.3f}) -> px ({x}, {y})")
        self.tap(x, y)

    def press_back(self):
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "keyevent", "4"],
            check=True,
        )

    def current_activity(self):
        result = subprocess.run(
            self._adb_prefix()
            + ["shell", "dumpsys", "window", "|", "grep", "-E", "mCurrentFocus"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        out = (result.stdout or "").strip()
        print(out if out else "  (couldn't read current focus)")
        return out


SKY_ARENA_PACKAGE = "com.com2us.smon.normal.freefull.google.kr.android.common"

# =====================================================================
# THE THREE CONSTANTS THAT MAKE THIS THE x1 RUN
# =====================================================================

# One tap on the speed button. A cold-started game is at x3, and the control
# cycles x1 -> x2 -> x3 -> x1, so one tap lands on x1.
SPEED_TAPS = 1

# The per-stage waits below were measured at x3.
#
# 1.0, because BATTLE_WAIT_BY_STAGE below now holds waits observed AT x1
# rather than x3 values waiting to be scaled up.
#
# Scaling never worked well. The speed setting scales the ANIMATION, not the
# whole battle: each turn also carries fixed cost - the camera cut, the damage
# popup, the gap between actions - and none of that shrinks. Worse, how much
# of a stage is animation varies from stage to stage, so no single factor
# fits. 3.0 then 2.0 both left runs idling on victory screens.
#
# Kept rather than deleted so this file stays copyable for the other speeds -
# but those need their own measured table, not this one times a factor.
SPEED_WAIT_MULTIPLIER = 1.0

# Log label and screenshot folder suffix only.
SPEED_LABEL = 1

# =====================================================================

LAUNCH_WAIT = 45

# Promo banners on the title screen. THREE today; it was TWO when this
# sequence was first mapped and the count changed on its own.
POPUP_CLOSE_FX, POPUP_CLOSE_FY = 0.800, 0.906
POPUP_COUNT = 3
POPUP_TAP_GAP = 2.0

TOUCH_TO_START_FX, TOUCH_TO_START_FY = 0.500, 0.840

# Two panels open after login and THE ORDER IS NOT FIXED, so both close
# buttons are tapped twice, alternating. Both points are harmless on the bare
# hub, which is what makes this safe without detecting which panel is on top.
GIFT_BOX_CLOSE_FX, GIFT_BOX_CLOSE_FY = 0.829, 0.154
SHOP_POPUP_CLOSE_FX, SHOP_POPUP_CLOSE_FY = 0.912, 0.122
LOGIN_PANEL_ROUNDS = 2
LOGIN_PANEL_GAP = 2.5

BATTLE_FX, BATTLE_FY = 0.604, 0.882
GAREN_FOREST_FX, GAREN_FOREST_FY = 0.258, 0.520
STAGE1_BATTLE_FX, STAGE1_BATTLE_FY = 0.888, 0.359

START_BATTLE_FX, START_BATTLE_FY = 0.836, 0.711

# ---------------------------------------------------------------------
# IN-BATTLE HUD
#
# Bottom left: settings gear, speed, auto-battle arrow. The row sits at 91.8%
# down - an earlier 93.4% grazed the bottom edge of the buttons, which is
# survivable on some framebuffers and not on others.
#
# AUTO resets when the app is launched, so it is tapped exactly once per run.
# Tapping it again on a later battle would switch it back off.
# ---------------------------------------------------------------------
BATTLE_SETTINGS_FX, BATTLE_SETTINGS_FY = 0.086, 0.918
BATTLE_SPEED_FX, BATTLE_SPEED_FY = 0.143, 0.918
BATTLE_AUTO_FX, BATTLE_AUTO_FY = 0.203, 0.918

SPEED_TAP_GAP = 2.0

# ---------------------------------------------------------------------
# BATTLE WAITS - observed AT x1, not derived from the x3 figures
#
# How long each stage actually needs at this speed, watched rather than
# calculated. They do not follow a smooth curve - stage 7 comes in under
# stage 4 - which is exactly why scaling one table into another kept
# overshooting: the share of a stage that is animation, and therefore the
# share the speed setting affects, varies from stage to stage.
#
# For reference, the x3 in-game clock read:
#     stage 1 Outskirts 00:04.472    stage 5           00:27.126
#     stage 2 South     00:22.809    stage 6 Plateau   00:28.217
#     stage 3 East      00:19.377    stage 7 Hollows   00:29.827
#     stage 4 Paths     00:27.061
#
# Overshooting only idles on a victory screen that waits for input forever;
# undershooting means the taps that follow land on a battle still in progress
# and the rest of the run is aimed at screens that are not there. So when one
# of these turns out to be short, raise that single entry.
# ---------------------------------------------------------------------
BATTLE_LOAD_WAIT = 12.0

BATTLE_WAIT_BY_STAGE = {
    1: 10.0,
    2: 30.0,
    3: 20.0,
    4: 50.0,
    5: 45.0,
    6: 50.0,
    7: 40.0,
}
DEFAULT_BATTLE_WAIT = 50.0


def battle_wait_for(stage: int) -> float:
    base = BATTLE_WAIT_BY_STAGE.get(stage, DEFAULT_BATTLE_WAIT)
    return base * SPEED_WAIT_MULTIPLIER


# Victory screen. Tapped several times on an empty spot because a LEVEL UP
# banner sometimes sits between the victory screen and the chest and eats one
# of the taps. The spot is the waterfall in the top left, chosen because the
# obvious patch of grass sits right above the Replay button and a stray tap
# there would start another battle.
VICTORY_DISMISS_FX, VICTORY_DISMISS_FY = 0.100, 0.280
VICTORY_TAPS = 6
VICTORY_TAP_GAP = 1.2
VICTORY_GAP = 4.0

DROP_POPUP_OK_FX, DROP_POPUP_OK_FY = 0.503, 0.832
DROP_GAP = 3.0

# Post-battle menu.
REPLAY_FX, REPLAY_FY = 0.359, 0.545
NEXT_STAGE_FX, NEXT_STAGE_FY = 0.647, 0.545
NEXT_STAGE_LOAD_WAIT = 6.0

# The right-hand slot says "Quit" instead of "Next Stage" after the last stage
# of the region - same position, same size, completely different action.
QUIT_FX, QUIT_FY = 0.647, 0.545
LAST_STAGE_IN_REGION = 7

STAGES_TO_ADVANCE = 6

# NEVER tap these. The download Collect starts a multi-GB download; the Level
# dropdown changes the workload; the x2 badges cost crystals or trigger an ad.
DOWNLOAD_COLLECT_FX, DOWNLOAD_COLLECT_FY = 0.503, 0.126
LEVEL_DROPDOWN_FX, LEVEL_DROPDOWN_FY = 0.845, 0.190
VICTORY_XP_X2_FX, VICTORY_XP_X2_FY = 0.831, 0.320
VICTORY_GEM_X2_FX, VICTORY_GEM_X2_FY = 0.902, 0.320

NEEDS_AUTO_TAP = False
SPEED_ALREADY_SET = False


def run_battle_cycle(c: AdbController, tag: str, stage: int):
    """Fight one battle, starting and ending on a known screen.

    ENTRY:  the TEAM SCREEN (the VS layout with Start Battle on the right).
    EXIT:   the POST-BATTLE MENU (Replay / Next Stage).

    Both ends wait for input indefinitely, which is what makes this safe to
    call in a loop - no timing dependency between one cycle and the next.

    Costs 3 energy per call and cannot be undone.
    """
    global NEEDS_AUTO_TAP, SPEED_ALREADY_SET

    wait = battle_wait_for(stage)
    print(f"  [{tag}] stage {stage} at x{SPEED_LABEL}: Start Battle "
          f"(battle wait {wait:.0f}s)")
    c.take_screenshot(f"{tag}_00_team.png")
    c.tap_frac(START_BATTLE_FX, START_BATTLE_FY)

    time.sleep(BATTLE_LOAD_WAIT)
    c.take_screenshot(f"{tag}_01_battle.png")

    # SPEED FIRST, AUTO SECOND - see the module docstring.
    if not SPEED_ALREADY_SET:
        c.take_screenshot(f"{tag}_02_speed_before.png")
        for i in range(1, SPEED_TAPS + 1):
            print(f"  [{tag}] speed tap {i}/{SPEED_TAPS} -> x{SPEED_LABEL}")
            c.tap_frac(BATTLE_SPEED_FX, BATTLE_SPEED_FY)
            time.sleep(SPEED_TAP_GAP)
        SPEED_ALREADY_SET = True
        # Keep this frame. The bottom left corner has to read x1, and it is
        # the only record that the run measured the speed it claims to.
        c.take_screenshot(f"{tag}_03_speed_after.png")

    if NEEDS_AUTO_TAP:
        print(f"  [{tag}] first battle since launch - enabling auto")
        c.tap_frac(BATTLE_AUTO_FX, BATTLE_AUTO_FY)
        NEEDS_AUTO_TAP = False
        time.sleep(2.0)

    time.sleep(wait)

    c.take_screenshot(f"{tag}_10_victory.png")

    print(f"  [{tag}] clearing victory ({VICTORY_TAPS} taps)")
    for _ in range(VICTORY_TAPS):
        c.tap_frac(VICTORY_DISMISS_FX, VICTORY_DISMISS_FY)
        time.sleep(VICTORY_TAP_GAP)

    time.sleep(VICTORY_GAP)
    print(f"  [{tag}] item popup -> OK")
    c.take_screenshot(f"{tag}_11_drop.png")
    c.tap_frac(DROP_POPUP_OK_FX, DROP_POPUP_OK_FY)
    time.sleep(DROP_GAP)

    c.take_screenshot(f"{tag}_12_menu.png")
    print(f"  [{tag}] done - should be on the post-battle menu")


if __name__ == "__main__":
    controller = AdbController()

    print("=== Step 1: Checking device connection ===")
    if not controller.check_connection():
        print("No device detected! Make sure the emulator is running and "
              "adb is configured correctly.")
        sys.exit(1)

    print(f"\n*** Battle speed for this run: x{SPEED_LABEL} "
          f"({SPEED_TAPS} tap(s) on the speed button, "
          f"waits x{SPEED_WAIT_MULTIPLIER}) ***")

    print("\n=== Step 2: Screen size ===")
    controller.screen_size()

    print("\n=== Step 3: Cold-starting Sky Arena ===")
    # Force-stop first. Auto-battle resets on launch and the speed goes back
    # to x3, which is what makes SPEED_TAPS correct. Bringing an
    # already-running game to the foreground would leave both wherever the
    # last run left them.
    controller.force_stop(SKY_ARENA_PACKAGE)
    time.sleep(2.0)
    controller.open_app(SKY_ARENA_PACKAGE)
    NEEDS_AUTO_TAP = True

    print(f"\n=== Step 4: Waiting {LAUNCH_WAIT}s for the title screen ===")
    time.sleep(LAUNCH_WAIT)
    controller.take_screenshot("01_launch.png")
    controller.current_activity()

    # Measured here, not earlier: the game has rotated the display to
    # landscape by now.
    print("\n=== Step 5: Measuring framebuffer ===")
    controller.framebuffer_size()

    print("\n=== Step 6: Dismissing the promo banners ===")
    for i in range(1, POPUP_COUNT + 1):
        controller.take_screenshot(f"10_popup_{i}_before.png")
        print(f"  closing banner {i}")
        controller.tap_frac(POPUP_CLOSE_FX, POPUP_CLOSE_FY)
        time.sleep(POPUP_TAP_GAP)
        controller.take_screenshot(f"11_popup_{i}_after.png")

    print("\n=== Step 7: Touch to Start ===")
    controller.take_screenshot("19_title_screen.png")
    controller.tap_frac(TOUCH_TO_START_FX, TOUCH_TO_START_FY)
    time.sleep(15)
    controller.take_screenshot("20_after_touch_to_start.png")

    print("\n=== Step 8: Clearing the login panels ===")
    for r in range(1, LOGIN_PANEL_ROUNDS + 1):
        controller.take_screenshot(f"30_login_panels_r{r}.png")
        print(f"  round {r}: offer panel X")
        controller.tap_frac(SHOP_POPUP_CLOSE_FX, SHOP_POPUP_CLOSE_FY)
        time.sleep(LOGIN_PANEL_GAP)
        print(f"  round {r}: gift box X")
        controller.tap_frac(GIFT_BOX_CLOSE_FX, GIFT_BOX_CLOSE_FY)
        time.sleep(LOGIN_PANEL_GAP)
    controller.take_screenshot("31_after_login_panels.png")

    print("\n=== Step 9: Opening the Battle menu ===")
    controller.tap_frac(BATTLE_FX, BATTLE_FY)
    time.sleep(8.0)
    controller.take_screenshot("40_battle_menu.png")

    print("\n=== Step 10: Entering Garen Forest ===")
    controller.tap_frac(GAREN_FOREST_FX, GAREN_FOREST_FY)
    time.sleep(8.0)
    controller.take_screenshot("50_garen_forest.png")

    print("\n=== Step 11: Stage 1 Outskirts -> team screen ===")
    controller.tap_frac(STAGE1_BATTLE_FX, STAGE1_BATTLE_FY)
    time.sleep(8.0)
    controller.take_screenshot("60_stage1_team.png")

    print(f"\n=== Step 12: Fighting the region at x{SPEED_LABEL} ===")
    run_battle_cycle(controller, "70_cycle1", 1)

    for n in range(1, STAGES_TO_ADVANCE + 1):
        stage = 1 + n
        print(f"\n  --- advancing to stage {stage} ---")
        controller.take_screenshot(f"80_adv{n}_00_menu.png")
        controller.tap_frac(NEXT_STAGE_FX, NEXT_STAGE_FY)
        time.sleep(NEXT_STAGE_LOAD_WAIT)
        run_battle_cycle(controller, f"80_adv{n}", stage)

    final_stage = 1 + STAGES_TO_ADVANCE
    print(f"\n=== Step 13: Quit (last fought stage was {final_stage}) ===")
    if final_stage >= LAST_STAGE_IN_REGION:
        controller.take_screenshot("90_last_menu.png")
        print("  tapping Quit")
        controller.tap_frac(QUIT_FX, QUIT_FY)
        time.sleep(5.0)
        controller.take_screenshot("91_after_quit.png")
    else:
        print(f"  skipped - stage {final_stage} is not the last in the region "
              f"({LAST_STAGE_IN_REGION}), so that slot is still Next Stage")

    print(f"\nDone. Ran at x{SPEED_LABEL}.")
    print("\nCheck 70_cycle1_03_speed_after.png - the bottom left corner has")
    print(f"to read x{SPEED_LABEL}. That frame is the only record that this")
    print("run measured the speed it claims to have measured.")