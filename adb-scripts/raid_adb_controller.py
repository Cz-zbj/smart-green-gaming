"""
raid_adb_controller.py

Bootstrap script for Raid: Shadow Legends, same "hands" module pattern as
sky_arena_adb_controller.py / adb_controller.py (Flow Free) /
mindustry_adb_controller.py / andors_tail_adb_controller.py - AdbController is
copy-pasted unchanged.

This is a BOOTSTRAP script, not the full automation. It only covers what can
be done before any screen has been measured: find the package, launch it,
wait, screenshot, confirm what's in the foreground. Once you send me the
screenshots this produces, we measure coordinates from them and extend the
script the same way sky_arena's was built up step by step.

USAGE
    python raid_adb_controller.py --find                 list candidate packages
    python raid_adb_controller.py --package <name>        open + screenshot
    python raid_adb_controller.py --package <name> --wait 60   longer launch wait
"""

import subprocess
import time
import os
import re
import sys


class AdbController:
    def __init__(self, device_id: str = None, screenshot_dir: str = "screenshots_raid"):
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

    def open_app(self, package_name: str):
        print(f"Attempting to open app: {package_name}")
        subprocess.run(
            self._adb_prefix()
            + ["shell", "monkey", "-p", package_name, "-c",
               "android.intent.category.LAUNCHER", "1"],
            check=True,
        )

    def list_packages(self, keyword: str = None):
        """Print installed packages, optionally filtered. Done in Python
        instead of `| grep` so it works the same on Windows."""
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
        """What `wm size` reports, parsed into (width, height). This is the
        device's NATURAL orientation (portrait here), so for a landscape
        game it will NOT match the screenshot dimensions."""
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
        """Actual width/height of what screencap produces, read straight from
        the PNG header. MUST be called while the screen is showing what you
        intend to measure - calling it too early records the wrong
        orientation for a landscape game, and that failure is silent: taps
        dispatch, adb exits 0, nothing on screen reacts."""
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

    def current_activity(self):
        """Which activity is in the foreground. Confirms the app actually
        launched instead of silently failing."""
        result = subprocess.run(
            self._adb_prefix() + ["shell", "dumpsys", "window"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        out = result.stdout or ""
        for line in out.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                print(line.strip())
        return out

    def dump_ui(self) -> str:
        """Raw uiautomator accessibility tree dump. If a game's UI is drawn
        inside a Unity/Canvas surface, this comes back basically empty (no
        matching nodes) - that tells us coordinates are the only option, the
        same conclusion FlowFreeUiTest.java's header comment reached for
        Flow Free."""
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

    def tap(self, x: int, y: int):
        print(f"Tapping at: ({x}, {y})")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "touchscreen", "tap", str(x), str(y)],
            check=True,
        )

    def framebuffer_size(self):
        """Actual width/height of what screencap produces, read straight from
        the PNG header. MUST be called while the screen is showing what you
        intend to measure - calling it too early records the wrong
        orientation for a landscape game, and that failure is silent: taps
        dispatch, adb exits 0, nothing on screen reacts."""
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

    def force_stop(self, package_name: str):
        """Close the game. Ends every run on a known state - and for the
        energy work it matters that the app isn't left running in the
        background after the measurement window closes."""
        print(f"Force-stopping {package_name}")
        subprocess.run(
            self._adb_prefix() + ["shell", "am", "force-stop", package_name],
            check=True,
        )

    def pixel_at_frac(self, path: str, fx: float, fy: float):
        """RGB of one point in a screenshot, given as framebuffer fractions.
        Returns None if Pillow is missing."""
        try:
            from PIL import Image
        except ImportError:
            return None
        with Image.open(path) as im:
            w, h = im.size
            x = min(int(round(fx * w)), w - 1)
            y = min(int(round(fy * h)), h - 1)
            return im.convert("RGB").getpixel((x, y))

    def press_back(self):
        """Android BACK key. Coordinate-free, so it works on dialogs whose
        close button we haven't measured - and most Unity modals wire it to
        the same action as their X."""
        print("Pressing BACK")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "keyevent", "4"],
            check=True,
        )

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 400):
        print(f"Swiping: ({x1}, {y1}) -> ({x2}, {y2})")
        subprocess.run(
            self._adb_prefix()
            + ["shell", "input", "touchscreen", "swipe",
               str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
            check=True,
        )

    def swipe_frac(self, fx1: float, fy1: float, fx2: float, fy2: float,
                   duration_ms: int = 400):
        """Swipe between two points given as framebuffer fractions."""
        if getattr(self, "fb_w", None) is None:
            raise RuntimeError("call framebuffer_size() first")
        x1 = int(round(fx1 * self.fb_w))
        y1 = int(round(fy1 * self.fb_h))
        x2 = int(round(fx2 * self.fb_w))
        y2 = int(round(fy2 * self.fb_h))
        print(f"  frac ({fx1:.3f},{fy1:.3f}) -> ({fx2:.3f},{fy2:.3f})")
        self.swipe(x1, y1, x2, y2, duration_ms)

    def tap_frac(self, fx: float, fy: float):
        """Tap a point given as a fraction of the framebuffer, e.g.
        (0.5, 0.5) is dead centre. Fractions instead of pixels so coordinates
        survive a different emulator resolution."""
        if getattr(self, "fb_w", None) is None:
            raise RuntimeError("call framebuffer_size() first")
        if self.fb_w < self.fb_h:
            raise RuntimeError(
                f"framebuffer is {self.fb_w}x{self.fb_h} (portrait) but this "
                "game is landscape - re-measure with the game on screen."
            )
        x = int(round(fx * self.fb_w))
        y = int(round(fy * self.fb_h))
        print(f"  frac ({fx:.3f}, {fy:.3f}) -> px ({x}, {y})")
        self.tap(x, y)

    def _fingerprint(self, path):
        """Downscale to 32x32 greyscale. Small enough that an animated
        background averages out, big enough that a different screen (or a
        popup gone) is obvious. Returns None if Pillow isn't installed."""
        try:
            from PIL import Image
        except ImportError:
            return None
        with Image.open(path) as im:
            return list(im.convert("L").resize((32, 32)).getdata())

    def screens_differ(self, path_a, path_b, threshold=6.0):
        """True if these two screenshots show a different screen (not just
        animation noise). None if Pillow is missing - caller decides what to
        do."""
        fa, fb = self._fingerprint(path_a), self._fingerprint(path_b)
        if fa is None or fb is None:
            return None
        diff = sum(abs(a - b) for a, b in zip(fa, fb)) / len(fa)
        print(f"  screen difference: {diff:.2f} (threshold {threshold})")
        return diff > threshold


# Confirmed via `adb shell pm list packages -3`.
RAID_PACKAGE = "com.plarium.raidlegends"

LAUNCH_WAIT = 45.0   # seconds to wait after launch before screenshotting

# ---------------------------------------------------------------------
# CLEARING PROMO POPUPS - NOT coordinate-hunting the X button.
#
# Three different popups seen so far on three separate launches (Silver
# Pack, Small Pack, Starter Pack), each a different size, each with its X
# in a different position - unlike Sky Arena, where every popup shared one
# X spot and a fixed-position loop was enough.
#
# But these are modal dialogs: they block input to whatever is under them,
# and a tap ANYWHERE on the dimmed background outside the dialog box
# dismisses it - confirmed by testing. So instead of measuring a new X
# position every time a new promo shows up, tap one fixed spot that is
# background in every popup seen so far (never inside the dialog box, never
# on one of the always-visible corner icons like Referral Program / Events
# / Purchase Rewards), and loop until the screen stops changing.
#
# SAFE_EMPTY_FX/FY = bottom-left corner, below the "Downloading" text and
# left of the SHOP button - empty dark background in every screenshot taken
# so far. Re-check this if a future screen turns out to have something live
# sitting there.
# ---------------------------------------------------------------------
SAFE_EMPTY_FX, SAFE_EMPTY_FY = 0.020, 0.970
POPUP_CLEAR_TAP_GAP = 1.5
# One budget for the whole clearing loop. Generous because overlays stack -
# a champion drop behind an unlock dialog behind a Level Up banner is three
# steps before the victory screen is even visible.
MAX_CLEAR_STEPS = 12
# Still used by the hub's own popup-clearing loop at step 2, which runs
# before any victory screen exists to check against.
MAX_POPUP_CLEAR_TAPS = 8

# ---------------------------------------------------------------------
# HUB BOTTOM BAR - measured from 02_popups_01.png (2856x1280 framebuffer).
# One tap on the safe corner was enough to clear the popup queue this run -
# landed straight on the hub with the bottom nav bar visible (SHOP,
# Missions, Quests, Challenges, Passes, Altar of Souls, Clans, Index,
# Champions, BATTLE).
# ---------------------------------------------------------------------
BATTLE_FX, BATTLE_FY = 0.898, 0.920
HUB_SETTLE_WAIT = 3.0
BATTLE_MENU_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# GAME MODES SCREEN - measured from 03_battle_menu.png. Five modes shown:
# Campaign, Dungeons, Faction Wars, Arena, Clan Bosses (more probably exist
# off-screen to the right, given the partial sixth card visible at the
# edge). ONLY CAMPAIGN IS UNLOCKED at this account's level (2) - the rest
# show a lock icon and a required LEVEL (6, 20, 6, 17). So Campaign is the
# only choice for now, not a preference - revisit if the account levels
# past those thresholds later.
# ---------------------------------------------------------------------
CAMPAIGN_CARD_FX, CAMPAIGN_CARD_FY = 0.163, 0.450
CAMPAIGN_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# CAMPAIGN MAP - measured from 04_campaign.png. Normal difficulty, Part
# 1/5. Stage 1 "Kaerok Castle" is already cleared (3 stars) - the account
# has played this before. Stage 2 "Sewers of Arnoc" is locked (needs stage
# 1's key first, most likely), stage 3 further out. Tapping the Kaerok
# Castle badge should open its team/prepare screen, same shape as Sky
# Arena's team screen before Start Battle.
# ---------------------------------------------------------------------
STAGE1_ICON_FX, STAGE1_ICON_FY = 0.473, 0.445
STAGE_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# KAEROK CASTLE STAGE LIST - measured from 05_stage1.png. Five sub-stages
# inside this location, each with its own Battle button (costs 4 energy).
# Stages 1-3 are unlocked and already cleared at 3 stars; 4-5 still locked.
# This is the equivalent of Sky Arena's per-region stage list.
#
# Tapping Battle here is NOT the same as Start Battle on the team screen -
# it's one step earlier, so it likely opens a team-selection screen next
# rather than starting combat immediately. Short load wait only, not the
# full battle-duration wait.
# ---------------------------------------------------------------------
STAGE1_BATTLE_FX, STAGE1_BATTLE_FY = 0.918, 0.180
BATTLE_BUTTON_LOAD_WAIT = 3.0

# ---------------------------------------------------------------------
# SCROLLING THE STAGE LIST BACK TO THE TOP
#
# The list opens wherever progress left it - confirmed showing stages 3-7
# with 1 and 2 scrolled off the top - so stage 1's Battle coordinate would
# hit whatever row happens to sit there instead. That is a silent failure
# of the worst kind: the tap works, a battle starts, energy is spent, and
# it's the wrong stage with the wrong expected duration.
#
# Swipe column is x=0.55: over the stage rows themselves, clear of the
# artifact/drops panel on the left (which scrolls independently) and clear
# of the Battle buttons on the right, so a swipe that gets interpreted as
# a tap doesn't start a battle. From high to low drags the content down,
# scrolling the view up toward stage 1.
#
# Deliberately a hard flick rather than a gentle drag: near-full-screen
# travel at 250ms, fast enough that the list keeps coasting after the
# finger lifts. A slow drag moves the list exactly as far as the finger
# and would need many more passes.
# ---------------------------------------------------------------------
SCROLL_FX = 0.550
SCROLL_FROM_FY = 0.150
SCROLL_TO_FY = 0.900
SCROLL_DURATION_MS = 250
SCROLL_SETTLE_GAP = 1.5    # flicks coast, so allow time to come to rest
MAX_SCROLL_SWIPES = 8

# ---------------------------------------------------------------------
# TEAM SCREEN - measured from 06_after_battle_tap.png. Team is already
# pre-filled (2 champions in the bottom slots, one marked LEADER) and auto
# battle at x2 speed is already the default here - unlike Sky Arena, where
# auto had to be tapped on after the first launch. Nothing to configure,
# Start just costs 4 energy per attempt.
#
# The same spot serves as both the stage list's Battle button and every
# team screen's Start button - they land in the same place.
# ---------------------------------------------------------------------
START_BATTLE_FX, START_BATTLE_FY = 0.865, 0.925

# ---------------------------------------------------------------------
# HOW LONG TO WAIT FOR EACH STAGE TO FINISH
#
# These are MINIMUMS, not the actual wait. The same stage does not take the
# same time twice - crits, misses and turn order vary, and the team levels
# up as the run progresses, so a stage gets faster over a session. Waiting
# a fixed number of seconds means either cutting a slow run short (every
# tap after it lands mid-battle and the cycle derails) or idling through
# every fast one.
#
# So the floor below is only "the battle definitely isn't over yet". After
# it expires, run_battle_cycle polls screenshots until the screen stops
# changing, which is what actually ends the wait. See wait_for_battle_end.
#
# The floors come from the in-game Best Times shown on the stage list
# (stage 3: 00:27, 4: 00:22, 5: 00:31, 6: 00:48, 7: 00:52) plus headroom,
# since Best is the FASTEST that stage has ever gone - a typical run is
# slower, and a fresh team slower still.
# ---------------------------------------------------------------------
BATTLE_WAIT_BY_STAGE = {
    1: 40.0,
    2: 45.0,
    3: 50.0,
    4: 45.0,
    5: 55.0,
    6: 85.0,
}
# For stages not yet timed. Stage 7's Best Time is 00:52, so this has room.
DEFAULT_BATTLE_WAIT = 105.0

# After the floor expires, poll until the screen holds still this many
# consecutive times - that's the battle being over and the victory screen
# sitting there waiting for input.
BATTLE_POLL_GAP = 3.0
BATTLE_POLL_STABLE_NEEDED = 2
BATTLE_POLL_TIMEOUT = 120.0
NEXT_STAGE_LOAD_WAIT = 4.0


def battle_wait_for(stage: int) -> float:
    """Seconds to wait for `stage` to finish fighting."""
    return BATTLE_WAIT_BY_STAGE.get(stage, DEFAULT_BATTLE_WAIT)

# ---------------------------------------------------------------------
# VICTORY SCREEN - measured from 07_after_wait.png. Shows the in-game clock
# (Time / Best) same as Sky Arena - free data, screenshot every run to pair
# exact duration with that run's energy figure.
#
# CONFIRMED: Next leads to a TEAM SCREEN for the next stage (08_after_next
# _immediate.png showed Stage 1-2's team screen, Start still costing 4
# energy, nothing charged yet) - NOT straight into battle. Same shape as
# Sky Arena's cycle: team screen -> Start -> battle -> victory -> Next ->
# next stage's team screen -> Start again. STAGE1_BATTLE_FX/FY and
# START_BATTLE_FX/FY are the same spot on every team screen seen so far, so
# one constant covers both the stage-list Battle tap and every team
# screen's Start tap.
# ---------------------------------------------------------------------
NEXT_STAGE_FX, NEXT_STAGE_FY = 0.918, 0.925

# How many stages step 7 fights in one run, starting from --stage.
#
# Each costs 4 energy and permanently advances progress, so a full 7-stage
# run needs 28 energy. Drop this to 1 while timing a NEW stage, so a wrong
# wait costs one battle instead of seven.
STAGES_TO_ADVANCE = 7


def parse_float_arg(argv, flag: str, default: float) -> float:
    if flag not in argv:
        return default
    i = argv.index(flag)
    if i + 1 >= len(argv):
        print(f"{flag} needs a number")
        sys.exit(1)
    return float(argv[i + 1])


def parse_int_arg(argv, flag: str, default: int) -> int:
    if flag not in argv:
        return default
    i = argv.index(flag)
    if i + 1 >= len(argv):
        print(f"{flag} needs a number")
        sys.exit(1)
    return int(argv[i + 1])


# ---------------------------------------------------------------------
# THE "X UNLOCKED!" DIALOG FAMILY
#
# Seen twice so far: "DUNGEONS UNLOCKED!" after stage 2 and "GREAT HALL
# UNLOCKED!" after stage 3. They fire when the account crosses a level
# threshold, so which stage triggers one is a property of progress, not of
# the stage - any cycle can end with one of these on top.
#
# CRUCIALLY, THEY SHARE ONE LAYOUT. Unlike the promo popups (every one a
# different size, X in a different place), these are the same template with
# different artwork: Skip bottom-left of the panel, Go beside it, X top
# right. So one measurement covers the whole family, including the ones
# that haven't appeared yet.
#
# They ignore background taps - the clearing loop tapped eight times with
# the screen difference stuck at 23 and never settled.
#
# SKIP, NEVER GO. Go navigates into the feature being advertised (the
# Dungeons list, the Great Hall) and abandons the battle loop entirely.
# Skip closes and leaves the game where it was.
#
# Detected by colour rather than tapped blind: SKIP_PROBE sits on the
# button's cyan fill, clear of the white lettering in the middle. Nothing
# else that appears at that spot on the victory or team screens is cyan, so
# a match means the dialog is up. Checking first is also what avoids
# burning eight useless background taps before escalating.
# ---------------------------------------------------------------------
UNLOCK_SKIP_FX, UNLOCK_SKIP_FY = 0.596, 0.841
UNLOCK_SKIP_PROBE_FX, UNLOCK_SKIP_PROBE_FY = 0.545, 0.841


def looks_like_unlock_dialog(controller: AdbController, path: str) -> bool:
    """Is an 'X UNLOCKED!' dialog on screen? Detected by the Skip button's
    cyan fill, measured at (20, 123, 156)."""
    rgb = controller.pixel_at_frac(path, UNLOCK_SKIP_PROBE_FX,
                                   UNLOCK_SKIP_PROBE_FY)
    if rgb is None:
        return False
    r, g, b = rgb
    cyan = b > 110 and g > 90 and b > r + 50
    if cyan:
        print(f"    unlock dialog detected (Skip probe rgb{rgb})")
    return cyan


def looks_like_victory(controller: AdbController, path: str) -> bool:
    """Is this screenshot the victory screen, or something else that just
    happens to be holding still?

    "The screen stopped changing" is NOT the same as "the overlay is gone".
    A static full-screen page that ignores background taps - the champion
    detail page that opened after stage 6 was the first one seen - looks
    exactly like a settled screen to a frame comparison: tap, nothing
    happens, two identical shots, loop declares success. Then Next's
    coordinates land on that page instead.

    So verify positively rather than inferring from stillness. The Next
    button is a saturated gold plate and sits where nothing else gold does
    on the pages that have been mistaken for it, which is enough to tell
    them apart without needing to recognise anything.

    Deliberately loose thresholds: the button has a gradient and a glow,
    and the emulator's colours aren't exact.
    """
    rgb = controller.pixel_at_frac(path, NEXT_STAGE_FX, NEXT_STAGE_FY)
    if rgb is None:
        return True    # can't check - assume ok rather than block the run
    r, g, b = rgb
    gold = r > 120 and g > 80 and b < 110 and r > b + 60
    print(f"    victory check at Next: rgb{rgb} -> {'yes' if gold else 'no'}")
    return gold


# ---------------------------------------------------------------------
# CHAMPION DETAIL PAGE - measured from 11_adv2_ovl_ov02.png.
#
# A full-screen page, not an overlay: opens when a battle drops a new
# champion ("NEW CHAMPION!" over the artwork), and also appeared after
# stage 6 for an already-owned one. Any stage can drop one, so this is not
# tied to a particular stage number.
#
# Identified by the gold X in the top-right corner against the dark blue
# header bar - a combination none of the other screens has in that spot.
# ---------------------------------------------------------------------
CHAMPION_X_FX, CHAMPION_X_FY = 0.970, 0.030


def looks_like_champion_page(controller: AdbController, path: str) -> bool:
    """Gold X on a dark header, top right - the champion detail page."""
    rgb = controller.pixel_at_frac(path, CHAMPION_X_FX, CHAMPION_X_FY)
    if rgb is None:
        return False
    r, g, b = rgb
    gold_x = r > 180 and g > 150 and b < 160 and r > b + 60
    if gold_x:
        print(f"    champion page detected (X probe rgb{rgb})")
    return gold_x


def identify_screen(controller: AdbController, path: str) -> str:
    """What is on screen right now?

    Returns one of: "victory", "unlock_dialog", "champion_page", "unknown".

    WHY IDENTIFY INSTEAD OF JUST TRYING THINGS. The earlier version worked
    down a ladder - background taps, then BACK, then give up - which meant
    paying twelve seconds of useless taps to discover a dialog that one
    pixel could have named immediately. Worse, it inferred success from the
    screen holding still, and a page that simply ignores taps holds just as
    still as a cleared one.
    
    WHY "unknown" IS A FIRST-CLASS ANSWER. Four different screens have
    turned up between a battle ending and Next becoming tappable: the Level
    Up banner, the "X UNLOCKED!" dialogs, the champion detail page, and the
    new-champion drop. There is no reason to think that list is finished -
    it grows with account progress, and each new one is invisible until the
    day it appears. So the recogniser is deliberately lopsided: it knows
    precisely what the GOAL looks like and has a shortcut for each screen
    already met, but anything unrecognised still gets handled generically
    rather than crashing the run.

    That asymmetry is the whole design. Recognising the destination is a
    fixed cost; enumerating everything in the way is not.
    """
    if looks_like_victory(controller, path):
        return "victory"
    if looks_like_unlock_dialog(controller, path):
        return "unlock_dialog"
    if looks_like_champion_page(controller, path):
        return "champion_page"
    return "unknown"


def clear_overlays(controller: AdbController, tag: str,
                   max_steps: int = MAX_CLEAR_STEPS,
                   gap: float = POPUP_CLEAR_TAP_GAP,
                   verify: bool = True) -> bool:
    """Get from wherever the screen is back to the victory screen.

    Each pass: look, name what's there, apply that screen's dismissal, look
    again. Loops because dismissing one thing routinely reveals another -
    a Level Up banner behind a champion drop behind an unlock dialog.

    Actions per screen:
      victory        done
      unlock_dialog  tap Skip (never Go - Go leaves for another menu)
      champion_page  tap its X
      unknown        tap the background, then BACK if that changed nothing

    BACK is the last resort rather than the first, because on a screen with
    nothing to dismiss it navigates AWAY - out of the stage list to the
    campaign map - and every coordinate afterwards lands somewhere wrong. A
    background tap on a bare screen is harmless; a stray BACK is not.
    """
    for step in range(1, max_steps + 1):
        shot = controller.take_screenshot(f"{tag}_clr{step:02d}.png")

        if not verify:
            return True

        screen = identify_screen(controller, shot)
        print(f"  [{tag}] step {step}: screen = {screen}")

        if screen == "victory":
            print(f"  [{tag}] on the victory screen after {step - 1} action(s)")
            return True

        if screen == "unlock_dialog":
            controller.tap_frac(UNLOCK_SKIP_FX, UNLOCK_SKIP_FY)
        elif screen == "champion_page":
            controller.tap_frac(CHAMPION_X_FX, CHAMPION_X_FY)
        else:
            # Unrecognised. Try the harmless thing first; if the screen
            # doesn't react at all, it's a page that needs BACK.
            controller.tap_frac(SAFE_EMPTY_FX, SAFE_EMPTY_FY)
            time.sleep(gap)
            after = controller.take_screenshot(f"{tag}_clr{step:02d}b.png")
            if controller.screens_differ(shot, after) is False:
                print(f"  [{tag}] tap changed nothing - pressing BACK")
                controller.press_back()

        time.sleep(gap)

    print(f"  [{tag}] gave up after {max_steps} steps - still not on the "
          f"victory screen. Check {tag}_clr*.png; there's a screen here "
          "that needs its own case in identify_screen().")
    return False


def scroll_stage_list_to_top(controller: AdbController, tag: str,
                             max_swipes: int = MAX_SCROLL_SWIPES) -> bool:
    """Scroll the stage list back to the top so stage 1 is visible.

    The list does NOT open at a fixed position: as the account clears
    stages, it opens scrolled down near the furthest unlocked one, so
    STAGE1_BATTLE_FX/FY - measured when the list happened to open at the
    top - lands on some other stage's Battle button. That is a silent
    failure of the worst kind: the tap works, a battle starts, 4 energy is
    spent, and it's the wrong stage with the wrong expected duration.

    Swiping DOWN (finger from upper to lower) drags the content down, which
    moves the view UP toward stage 1.

    Repeats until two consecutive screenshots match, i.e. the list won't
    scroll any further, rather than assuming a fixed number of swipes -
    same technique as clear_overlays. Returns True if the top was
    confirmed reached.
    """
    prev = controller.take_screenshot(f"{tag}_scroll00.png")
    for i in range(1, max_swipes + 1):
        controller.swipe_frac(SCROLL_FX, SCROLL_FROM_FY,
                              SCROLL_FX, SCROLL_TO_FY,
                              SCROLL_DURATION_MS)
        time.sleep(SCROLL_SETTLE_GAP)
        cur = controller.take_screenshot(f"{tag}_scroll{i:02d}.png")
        differs = controller.screens_differ(prev, cur)
        if differs is None:
            print("  Pillow not installed - can't detect the top of the list")
            return False
        if not differs:
            print(f"  [{tag}] list at top after {i} swipe(s)")
            return True
        prev = cur
    print(f"  [{tag}] list still moving after {max_swipes} swipes - check "
          f"{tag}_scroll*.png by hand")
    return False


def wait_for_battle_end(controller: AdbController, tag: str, stage: int
                        ) -> float:
    """Wait out a battle, then poll until the screen settles.

    Two phases:
      1. Sleep the stage's floor from BATTLE_WAIT_BY_STAGE - long enough
         that the battle is definitely still running, so the poll below
         can't mistake a mid-battle lull for the end.
      2. Screenshot every BATTLE_POLL_GAP seconds until two consecutive
         shots match, meaning nothing is animating any more: the fight is
         over and the victory screen is sitting there waiting for input.

    This is what makes the timing robust against the same stage running
    fast one time and slow the next. A fixed sleep has to be set for the
    worst case and then wastes that margin on every other run; this pays
    only for what the battle actually took.

    Careful about phase 1's length: the poll cannot distinguish "battle
    finished" from "battle paused on a slow animation", so the floor has
    to clear the point where a battle could look still. That's why the
    floors track the in-game Best Times rather than being set to zero.

    Returns roughly how many seconds were spent, for the log.
    """
    floor = battle_wait_for(stage)
    print(f"  [{tag}] battle floor {floor:.0f}s, then polling")
    time.sleep(floor)

    prev = controller.take_screenshot(f"{tag}_poll00.png")
    stable = 0
    waited = 0.0
    i = 0
    while waited < BATTLE_POLL_TIMEOUT:
        time.sleep(BATTLE_POLL_GAP)
        waited += BATTLE_POLL_GAP
        i += 1
        cur = controller.take_screenshot(f"{tag}_poll{i:02d}.png")
        differs = controller.screens_differ(prev, cur)
        if differs is None:
            print("  Pillow not installed - falling back to the floor alone")
            return floor
        stable = 0 if differs else stable + 1
        prev = cur
        if stable >= BATTLE_POLL_STABLE_NEEDED:
            total = floor + waited
            print(f"  [{tag}] battle settled after {total:.0f}s total "
                  f"({waited:.0f}s past the floor)")
            return total
    print(f"  [{tag}] still animating {BATTLE_POLL_TIMEOUT:.0f}s past the "
          "floor - continuing anyway, check the poll frames")
    return floor + waited


def run_battle_cycle(controller: AdbController, tag: str,
                     stage: int) -> None:
    """Fight one stage, starting and ending on a known screen.

    ENTRY:  a TEAM SCREEN (the VS layout with Start bottom-right).
    EXIT:   that stage's VICTORY screen, overlays cleared, Next tappable.

    Both ends wait for input indefinitely, so this is safe to call in a
    loop - no timing dependency between one cycle and the next. Same shape
    as sky_arena's run_battle_cycle.

    `stage` picks the wait FLOOR from BATTLE_WAIT_BY_STAGE - the point past
    which the battle is definitely still running. After that the wait is
    adaptive: it polls until the screen settles, so a fast run doesn't idle
    and a slow one doesn't get cut short. `stage` is passed in rather than
    detected, because nothing on screen tells the script which stage it's
    on, and the floors are not interpolatable (stage 4 is shorter than
    stage 3).

    Costs 4 energy per call and permanently advances progress.

    Screenshots kept per cycle:
      {tag}_00_team.png     what team fought, at what levels
      {tag}_10_victory.png  the in-game clock (Time/Best) + post-battle levels

    The victory frame matters for the same reason it did in Sky Arena: the
    game times the fight for us to the second, so each energy figure can be
    paired with the exact battle duration it covers, instead of assuming
    every run of "stage N" took the same time.
    """
    wait = battle_wait_for(stage)
    print(f"  [{tag}] stage {stage}: team screen -> Start "
          f"(floor {wait:.0f}s, then adaptive)")
    controller.take_screenshot(f"{tag}_00_team.png")
    controller.tap_frac(START_BATTLE_FX, START_BATTLE_FY)

    wait_for_battle_end(controller, tag, stage)

    # A Level Up banner sometimes covers the victory screen (seen on stage
    # 2, which took the account to level 3). Clear whatever is on top
    # before the caller tries to tap Next.
    clear_overlays(controller, f"{tag}_ovl")
    controller.take_screenshot(f"{tag}_10_victory.png")
    print(f"  [{tag}] done - victory screen, Next should be tappable")


def advance_to_next_stage(controller: AdbController, tag: str,
                          load_wait: float = NEXT_STAGE_LOAD_WAIT) -> None:
    """Victory screen -> next stage's TEAM SCREEN.

    Next does NOT go straight into combat - it lands on the next stage's
    team screen and still needs a Start tap, confirmed from
    08_after_next_immediate.png. So this pairs with run_battle_cycle rather
    than replacing it.
    """
    print(f"  [{tag}] tapping Next (4 energy)")
    controller.tap_frac(NEXT_STAGE_FX, NEXT_STAGE_FY)
    time.sleep(load_wait)
    controller.take_screenshot(f"{tag}_20_next_team.png")


if __name__ == "__main__":
    controller = AdbController()
    launch_wait = parse_float_arg(sys.argv, "--wait", LAUNCH_WAIT)
    # --from lets you re-run from a later step without relaunching the app -
    # the emulator keeps its state between runs, same as every other game
    # script here. --from 2 assumes the game is ALREADY showing 01_launch.png
    # (i.e. the popup from this run is still on screen).
    START = parse_int_arg(sys.argv, "--from", 1)
    # Which stage the FIRST battle of this run fights. Only used by step 11,
    # to look up the right wait. Cannot be read off the screen, and getting
    # it wrong means waiting the wrong amount for that battle.
    STAGE = parse_int_arg(sys.argv, "--stage", 1)

    print("=== Checking device connection ===")
    if not controller.check_connection():
        print("No device detected! Make sure the emulator is running and "
              "adb is configured correctly.")
        sys.exit(1)

    if "--dump-ui" in sys.argv:
        print("\n=== Dumping current uiautomator accessibility tree ===")
        xml = controller.dump_ui()
        out_path = os.path.join(controller.screenshot_dir, "ui_dump.xml")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(xml)
        print(f"Saved to {out_path} ({len(xml)} chars)")
        if len(xml.strip()) < 200:
            print("Very little content came back - likely means this "
                  "screen is drawn inside a Unity/Canvas surface with no "
                  "accessible nodes, same as Flow Free. Coordinates it is.")
        sys.exit(0)

    if START <= 1:
        print(f"\n=== Step 1: Opening {RAID_PACKAGE} ===")
        controller.open_app(RAID_PACKAGE)

        print(f"\n=== Waiting {launch_wait:.0f}s for launch ===")
        time.sleep(launch_wait)

        print("\n=== Screenshot ===")
        controller.take_screenshot("01_launch.png")
    else:
        print(f"\n*** --from {START}: skipping launch. Game must ALREADY be "
              "showing what this step expects. ***")

    print("\n=== Measuring framebuffer (game must be on screen) ===")
    controller.framebuffer_size()

    if START <= 2:
        print("\n=== Step 2: Clearing promo popups (tap empty corner, "
              "loop until stable) ===")
        prev = controller.take_screenshot("02_popups_00.png")
        cleared = False
        for i in range(1, MAX_POPUP_CLEAR_TAPS + 1):
            controller.tap_frac(SAFE_EMPTY_FX, SAFE_EMPTY_FY)
            time.sleep(POPUP_CLEAR_TAP_GAP)
            cur = controller.take_screenshot(f"02_popups_{i:02d}.png")
            differs = controller.screens_differ(prev, cur)
            if differs is None:
                print("  Pillow not installed - can't auto-detect when "
                      "clear. Install with: pip install pillow")
                break
            if not differs:
                print(f"  screen stopped changing after {i} tap(s) - "
                      "popup queue looks clear")
                cleared = True
                break
            prev = cur
        if not cleared:
            print(f"  still changing after {MAX_POPUP_CLEAR_TAPS} taps - "
                  "either more popups than expected, or the safe spot "
                  "isn't actually background on some screen. Check the "
                  "02_popups_*.png sequence.")

    if START <= 3:
        print("\n=== Step 3: Opening Battle menu ===")
        time.sleep(HUB_SETTLE_WAIT)
        controller.tap_frac(BATTLE_FX, BATTLE_FY)
        time.sleep(BATTLE_MENU_LOAD_WAIT)
        controller.take_screenshot("03_battle_menu.png")
        time.sleep(BATTLE_MENU_LOAD_WAIT)
        controller.take_screenshot("03_battle_menu_settled.png")

    if START <= 4:
        print("\n=== Step 4: Entering Campaign (only unlocked mode) ===")
        controller.tap_frac(CAMPAIGN_CARD_FX, CAMPAIGN_CARD_FY)
        time.sleep(CAMPAIGN_LOAD_WAIT)
        controller.take_screenshot("04_campaign.png")
        time.sleep(CAMPAIGN_LOAD_WAIT)
        controller.take_screenshot("04_campaign_settled.png")

    if START <= 5:
        print("\n=== Step 5: Opening stage 1 (Kaerok Castle) ===")
        controller.tap_frac(STAGE1_ICON_FX, STAGE1_ICON_FY)
        time.sleep(STAGE_LOAD_WAIT)
        controller.take_screenshot("05_stage1.png")
        time.sleep(STAGE_LOAD_WAIT)
        controller.take_screenshot("05_stage1_settled.png")

    if START <= 6:
        print("\n=== Step 6: Scrolling stage list to top, then tapping "
              "Stage 1 Battle (4 energy) ===")
        # The list opens scrolled to wherever progress left it, so stage
        # 1's Battle coordinate is only correct once we're back at the top.
        scroll_stage_list_to_top(controller, "06")
        controller.tap_frac(STAGE1_BATTLE_FX, STAGE1_BATTLE_FY)
        time.sleep(BATTLE_BUTTON_LOAD_WAIT)
        controller.take_screenshot("06_after_battle_tap.png")

    if START <= 7:
        print(f"\n=== Step 7: Fighting stages {STAGE}.."
              f"{STAGE + STAGES_TO_ADVANCE - 1} ===")
        # ENTRY: a TEAM SCREEN for stage STAGE.
        #   - from a full run, step 6's Battle tap put us on stage 1's
        #   - from --from 7 --stage N, the game must already be showing
        #     stage N's team screen
        #
        # Each iteration fights the current stage, then taps Next to land
        # on the following stage's team screen - so the loop's entry
        # condition holds again at the top of the next pass. 4 energy each,
        # and progress is permanent.
        #
        # No Next after the LAST stage: that would spend 4 energy opening a
        # team screen nothing is waiting to fight, and leave the game on a
        # different screen than the loop's own exit point.
        for n in range(STAGES_TO_ADVANCE):
            stage_num = STAGE + n
            print(f"\n  --- stage {stage_num} "
                  f"({n + 1}/{STAGES_TO_ADVANCE}) ---")
            run_battle_cycle(controller, f"07_s{stage_num}", stage_num)
            if n < STAGES_TO_ADVANCE - 1:
                advance_to_next_stage(controller, f"07_s{stage_num}")

    if START <= 8:
        print("\n=== Step 8: Closing the game ===")
        # Every run ends the same way, whatever happened during it. Leaving
        # the app running would keep it drawing and talking to the network
        # after the measurement window has closed, which would land in
        # whatever the next thing measured is.
        controller.take_screenshot("08_before_exit.png")
        controller.force_stop(RAID_PACKAGE)
        time.sleep(2.0)

    print("\nDone. Send me the latest screenshots_raid/*.png file.")
    print("Battle waits calibrated so far (+5s headroom included):")
    for s in sorted(BATTLE_WAIT_BY_STAGE):
        print(f"    stage {s}: {BATTLE_WAIT_BY_STAGE[s]:.0f}s")
    print(f"    untimed stages: {DEFAULT_BATTLE_WAIT:.0f}s")
    print("\nNext runs:")
    print(f"    python {os.path.basename(__file__)}")
    print("        full run from launch, fights stages "
          f"{STAGE}..{STAGE + STAGES_TO_ADVANCE - 1}")
    print(f"    python {os.path.basename(__file__)} --from 7 --stage N")
    print("        skip navigation; game must already be on stage N's "
          "team screen")