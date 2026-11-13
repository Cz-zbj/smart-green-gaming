"""
sky_arena_adb_controller.py

Same "hands" module as adb_controller.py (Flow Free) /
mindustry_adb_controller.py / andors_tail_adb_controller.py - AdbController is
copy-pasted unchanged so every game script shares one implementation.

USAGE
    python sky_arena_adb_controller.py                    full run, stage 1
    python sky_arena_adb_controller.py --from 13 --stage 2   fight stage 2
    python sky_arena_adb_controller.py --from 14 --stage 2   -> stage 3, fight
    python sky_arena_adb_controller.py --find             list packages

--stage tells the script which stage the first battle of this run is, so it
knows how long to wait for the fighting to finish (BATTLE_WAIT_BY_STAGE). It
cannot be detected from the screen, and getting it wrong is not harmless: a
wait that is too short means the taps that follow land on a battle still in
progress.

--from exists because the emulator KEEPS ITS STATE between runs. Once the game
is sitting on the hub there is no reason to spend 45s on the launch wait and
another ~10s dismissing banners that are already gone - those steps would
either do nothing or, worse, tap the hub at the banner's coordinates and open
something unexpected.

Rule of thumb: --from N means "the screen is already showing what step N
expects to see". If it isn't, taps land on the wrong screen, which looks
exactly like the game ignoring input.

STEP NUMBERS CHANGED. What used to be steps 13-16 (Start Battle, auto, clear
victory, clear drop popup) are now one function, run_battle_cycle(), because
advancing through stages repeats all four every time. Step 13 runs one cycle;
step 14 advances to the next stage and runs a cycle, STAGES_TO_ADVANCE times.
"""

import subprocess
import time
import os
import re
import sys
import xml.etree.ElementTree as ET


# How every tap is delivered. Flip this one constant if taps stop registering.
#
#   "instant" -> input touchscreen tap x y
#                zero-duration press. What the calibration run's attempt 01
#                used, and the current default.
#
#   "held"    -> input touchscreen swipe x y x y 150
#                press and hold for TAP_HOLD_MS. Survives a low frame rate,
#                where an engine polling input once per frame can miss a
#                gesture that starts and ends inside a single frame.
#
# Note the `touchscreen` source in BOTH. That part is not optional: plain
# `input tap` lets Android choose the input device, and on an emulator with
# several it can choose one the game never reads - the command still exits 0.
TAP_MODE = "instant"
TAP_HOLD_MS = 150


class AdbController:
    def __init__(self, device_id: str = None, screenshot_dir: str = "screenshots_sky_arena"):
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
        """Deliver a tap using whichever style TAP_MODE selects.

        Every tap in the script goes through here, so switching the constant
        at the top of the file changes the whole run - menus, popups, in-game
        actions - rather than needing edits at each call site.
        """
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
        """A tap that lasts. `input swipe` from a point to the SAME point is
        a press-and-hold at one spot."""
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
        """Wipe saves/preferences so every run starts from an identical state.
        Not used yet - only matters once we start measuring energy, but the
        lesson from Andor's Trail is that a save file shifts menu coordinates,
        so plan for it from the start."""
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

    # -----------------------------------------------------------------
    # Helpers used to bootstrap a NEW game script
    # -----------------------------------------------------------------
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
        """What `wm size` reports, parsed into (width, height). Careful: this
        is the device's NATURAL orientation (portrait here), so for a
        landscape game it does NOT match the screenshot dimensions."""
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
        the PNG header - bytes 16..24 of any PNG are width and height as
        big-endian uint32. No PIL needed.

        MUST be called while the screen is showing what you intend to tap.
        This game is landscape but the device is portrait at rest, so calling
        this before the game has launched records 1280x2856 and every
        fraction below then resolves to a point in the wrong orientation.
        That is a silent failure: the taps are dispatched, adb exits 0, and
        nothing on screen reacts.
        """
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
        """Tap a point given as a fraction of the framebuffer, e.g.
        (0.5, 0.5) is dead centre.

        Fractions instead of pixels because this game is landscape and the
        emulator's framebuffer dimensions are not the ones `wm size` reports -
        writing raw pixels here would bake in one specific emulator config,
        exactly the thing that made the earlier scripts fragile.

        Refuses to run against portrait dimensions rather than tapping a
        wrong point quietly. A wrong tap looks exactly like a game that
        ignored the input, which sends you debugging the wrong thing.
        """
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

    # -----------------------------------------------------------------
    # Stable-screen polling (same idea as the Mindustry script)
    # -----------------------------------------------------------------
    def _fingerprint(self, path):
        """Downscale to 32x32 greyscale and return the pixel list. Small
        enough that an animated background averages out, big enough that a
        whole different screen is obvious.

        Needs Pillow. Returns None if it isn't installed, and the callers
        fall back to fixed waits."""
        try:
            from PIL import Image
        except ImportError:
            return None
        with Image.open(path) as im:
            return list(im.convert("L").resize((32, 32)).getdata())

    def screens_differ(self, path_a, path_b, threshold=6.0):
        """True if these two screenshots show different SCREENS.

        Not a byte comparison - the title screen has a drifting animated
        background, so two shots of the same screen are never identical
        byte-for-byte. Mean absolute difference over the 32x32 thumbnail
        stays low (a few units) for the same screen and jumps well past the
        threshold when the artwork changes."""
        fa, fb = self._fingerprint(path_a), self._fingerprint(path_b)
        if fa is None or fb is None:
            return None    # Pillow missing - caller decides what to do
        diff = sum(abs(a - b) for a, b in zip(fa, fb)) / len(fa)
        print(f"  screen difference: {diff:.2f} (threshold {threshold})")
        return diff > threshold

    def wait_until_stable(self, label, poll=1.5, stable_needed=2, timeout=25):
        """Screenshot repeatedly until two consecutive shots show the same
        screen, i.e. animations have settled. Returns the last path.

        This is the fix for taps being swallowed: instead of guessing a sleep
        long enough to outlast a fade-in, we watch until the fade is over."""
        prev = self.take_screenshot(f"_stable_{label}_0.png")
        stable = 0
        waited = 0.0
        while waited < timeout:
            time.sleep(poll)
            waited += poll
            cur = self.take_screenshot(f"_stable_{label}_1.png")
            differs = self.screens_differ(prev, cur)
            if differs is None:
                print("  Pillow not installed - falling back to a fixed wait")
                time.sleep(2.0)
                return cur
            stable = 0 if differs else stable + 1
            prev = cur
            if stable >= stable_needed:
                print(f"  screen stable after {waited:.1f}s")
                return cur
        print(f"  still animating after {timeout}s - continuing anyway")
        return prev

    def current_activity(self):
        """Which activity is in the foreground. Useful to confirm the app
        actually launched instead of silently failing."""
        result = subprocess.run(
            self._adb_prefix()
            + ["shell", "dumpsys", "window", "|", "grep", "-E", "mCurrentFocus"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        out = (result.stdout or "").strip()
        print(out if out else "  (couldn't read current focus)")
        return out


# ---------------------------------------------------------------------
# Confirmed via `adb shell pm list packages -3`
#
# "Sky Arena" here is Summoners War: Sky Arena (Com2uS). The package name
# carries the store/region it was built for (google.kr), which is normal for
# Com2uS builds and not a problem.
#
# NOTE - do NOT call clear_app_data() on this one without thinking. Unlike
# Flow Free or Andor's Trail, this is an online game: wiping data throws away
# the account AND several GB of downloaded assets. Determinism for the energy
# runs has to come from starting each run at a fixed in-game screen instead of
# a fixed install state.
# ---------------------------------------------------------------------
SKY_ARENA_PACKAGE = "com.com2us.smon.normal.freefull.google.kr.android.common"

LAUNCH_WAIT = 45
SETTLE_SHOTS = 0
SETTLE_WAIT = 15

# ---------------------------------------------------------------------
# PROMO POPUP - re-measured from 10_popup_close_1.png
#
# We tap the X and DELIBERATELY never touch the checkbox. Ticking it would
# make run #1 (popup shown) differ from run #2 (popup suppressed), and the
# suppression expires at midnight, so runs would also differ by time of day.
# ---------------------------------------------------------------------
POPUP_CLOSE_FX, POPUP_CLOSE_FY = 0.800, 0.906
POPUP_DONTSHOW_FX, POPUP_DONTSHOW_FY = 0.199, 0.906   # NOT USED, see above
POPUP_COUNT = 3    # was 2 when written; the game changed it on its own
POPUP_TAP_GAP = 2.0

TOUCH_TO_START_FX, TOUCH_TO_START_FY = 0.500, 0.840

# ---------------------------------------------------------------------
# LOGIN PANELS - measured from 20_after_touch_to_start.png and
# 31_after_gift_box.png
#
# Logging in opens two panels over the hub, and THE ORDER IS NOT FIXED. The
# Gift Box came first when the sequence was originally mapped; the monthly
# offer panel ("Special Price Package of the Month!") now usually comes first,
# but not always.
#
# Handled by tapping both close buttons twice, alternating:
#
#     shop X  ->  gift X  ->  shop X  ->  gift X
#
# Whichever panel is on top, one of the taps in the first pass lands on it,
# and the second pass collects whatever was underneath. Both points are
# harmless on the bare hub, which is what makes this safe without having to
# work out which panel is showing.
#
# Cheaper and more robust than detecting the order, and the alternative -
# assuming an order - is exactly the kind of assumption this game keeps
# breaking. Sixth case so far, after the banner count going 2 -> 3, the
# download size going 773MB -> 2102MB, the team growing from two monsters to
# three, the Next Stage slot turning into Quit, and this offer panel appearing
# at all.
#
# NOTHING ELSE ON EITHER PANEL IS TOUCHED. The Gift Box Collect buttons would
# claim rewards and change the account, so run #2 would start from a different
# state than run #1. The offer panel's Buy buttons open a real payment flow -
# their coordinates are not recorded anywhere, so a typo cannot reach them.
#
# The offer is dated (14 days), so it will disappear on its own. The taps
# aimed at it will then be harmless no-ops, which is why this comment exists:
# without it nobody will understand later why the login sequence taps a spot
# where nothing has ever been.
# ---------------------------------------------------------------------
GIFT_BOX_CLOSE_FX, GIFT_BOX_CLOSE_FY = 0.829, 0.154
SHOP_POPUP_CLOSE_FX, SHOP_POPUP_CLOSE_FY = 0.912, 0.122
LOGIN_PANEL_ROUNDS = 2
LOGIN_PANEL_GAP = 2.5
POST_LOGIN_SHOTS = 1
POST_LOGIN_GAP = 4.0

# HUB BOTTOM BAR - measured from 34_hub_t12s.png
BATTLE_FX, BATTLE_FY = 0.604, 0.882
MONSTER_FX, MONSTER_FY = 0.681, 0.882
MISSION_FX, MISSION_FY = 0.758, 0.882
COMMUNITY_FX, COMMUNITY_FY = 0.836, 0.882
SHOP_FX, SHOP_FY = 0.913, 0.882

# WORLD MAP - measured from 41_battle_menu_settled.png. Aimed at the island
# body, not the label - the label sits near the bottom edge of the landmass
# and a tap a few pixels low lands on the map background.
GAREN_FOREST_FX, GAREN_FOREST_FY = 0.258, 0.520

# ---------------------------------------------------------------------
# STAGE LIST - measured from 51_garen_forest_settled.png
#
# Rows are evenly spaced, hence the constant ~0.184 between fy values. Only
# stages 1-3 were unlocked when this was measured; clearing stages unlocks
# more and the panel scrolls, so only these three can be trusted without
# re-measuring.
#
# Energy: 3 per battle, cap 132 after the summoner levelled - about 40 battles
# before waiting on the refill.
# ---------------------------------------------------------------------
STAGE1_BATTLE_FX, STAGE1_BATTLE_FY = 0.888, 0.359   # 1. Outskirts
STAGE2_BATTLE_FX, STAGE2_BATTLE_FY = 0.888, 0.543   # 2. South
STAGE3_BATTLE_FX, STAGE3_BATTLE_FY = 0.888, 0.727   # 3. East
STAGE_PANEL_CLOSE_FX, STAGE_PANEL_CLOSE_FY = 0.928, 0.086

# ---------------------------------------------------------------------
# TEAM SCREEN - measured from 61_stage1_battle_settled.png, re-confirmed on
# stage 2 in 100_next_stage_start.png (same layout, so these hold).
#
# THE ROSTER IS NEVER TOUCHED - but that is NOT enough to keep the team fixed,
# which is a correction to what this comment said earlier.
#
# Stage 1 fought with TWO monsters. Stage 2 opened with THREE already ticked,
# without a single tap from us: the number of usable slots grows with
# progress, and the game fills the new slot by itself. Levels moved too, 10/10
# to 11/11/9.
#
# So the team composition is a function of account progress, not of what the
# script does. Fourth independent case of the same phenomenon, after the
# banner count (2 -> 3), the download size (773MB -> 2102MB) and the
# conditional drop popup. In a live service game with progression, "identical
# workload across runs" is not achievable by being careful with taps - it has
# to be measured and reported, not assumed.
#
# Practical consequence: capture this screen every run. It shows how many
# monsters, which ones, and at what level, which is the record of what the
# workload actually was.
# ---------------------------------------------------------------------
START_BATTLE_FX, START_BATTLE_FY = 0.836, 0.711
CANCEL_BATTLE_FX, CANCEL_BATTLE_FY = 0.836, 0.882

# ---------------------------------------------------------------------
# IN-BATTLE HUD - measured from 70_battle_t010s.png
#
# AUTO IS A TOGGLE, NOT A BUTTON. Sky Arena remembers the auto state across
# battles, so a script that blindly taps it every run turns auto ON for run 1
# and OFF again for run 2. In the data that looks like wild unexplained
# variance rather than a bug.
#
# SPEED IS ALSO PERSISTENT and reads x3. Never tapped. It belongs in the
# report: "all measurements at x3 battle speed with auto-battle enabled".
#
# The skill icons are recorded but NOT used. Auto picks skills with the game's
# own fixed policy, which is more consistent than any hardcoded tap sequence -
# turn order depends on speed stats and RNG, so a fixed sequence would
# desynchronise within a few turns. Manual skill selection is the right demo
# for the model-driven phase later; today it would only add ADB input events a
# real player would not generate, inflating the number we measure.
# ---------------------------------------------------------------------
BATTLE_SETTINGS_FX, BATTLE_SETTINGS_FY = 0.086, 0.934
BATTLE_SPEED_FX, BATTLE_SPEED_FY = 0.143, 0.934      # reads x3 - do not tap
BATTLE_AUTO_FX, BATTLE_AUTO_FY = 0.203, 0.934
SKILL1_FX, SKILL1_FY = 0.844, 0.930                  # recorded, not used
SKILL2_FX, SKILL2_FY = 0.918, 0.930                  # recorded, not used

# AUTO RESETS WHEN THE APP IS LAUNCHED, AND ONLY THEN.
#
# Established by watching it rather than by guessing, after two wrong guesses.
# First guess: the setting persists forever, so never tap it - that stranded a
# battle sitting idle waiting for skill taps. Second guess: it resets every
# battle, so tap it every time - that would turn auto back OFF on any battle
# where it was still on.
#
# What actually happens: a freshly launched game starts with auto off, and the
# first tap turns it on for the rest of the session. Every battle after that
# is automatic without being told.
#
# So the tap is tied to the APP LAUNCH, not to the battle. This invocation
# launched the app only if it ran step 3, which is exactly when the toggle
# needs pressing. A --from 13 or --from 14 run reuses a game that has been
# open since earlier, where auto is already on and must not be touched.
#
# The flag below is set in __main__ from the start step and cleared by the
# first battle cycle that uses it.
NEEDS_AUTO_TAP = False

# ---------------------------------------------------------------------
# HOW LONG TO WAIT FOR A BATTLE TO FINISH
#
# The calibration run's victory screen read TIME 00:24.408, but that number
# was contaminated by us: auto was still off, so the battle sat idle waiting
# for skill taps for most of those 24 seconds, and the in-game clock counts
# wall time rather than time spent fighting.
#
# With auto on, the real durations are:
#
#     stage 1  Outskirts   TIME 00:04.472   -> wait 8s
#     stage 2  South       TIME 00:22.809 / 00:16.127   -> wait 20s
#     stage 3  East        TIME 00:19.377   -> wait 20s
#     stage 4  Paths       TIME 00:27.061   -> wait 30s
#     stage 5              TIME 00:27.126   -> wait 30s
#     stage 6  Plateau     TIME 00:28.217   -> wait 30s
#     stage 7  Hollows     TIME 00:29.827   -> wait 45s
#
# Stage 7 gets 45s rather than the ~35s its clock would suggest because an
# animation plays between the end of the fighting and the victory screen being
# ready for taps. The in-game clock stops before that animation does, so on
# the later stages the clock is a floor for the wait, not the wait itself.
#
# The curve rises then flattens hard: a big step from stage 1 to stage 2, then
# stages 4, 5 and 6 landing inside a 1.2s band. Two forces pull against each
# other - stages get harder with depth, and the team gets stronger with every
# battle fought (Lv11 at stage 2, Lv14 by stage 5). On the plateau they
# roughly cancel.
#
# THAT PLATEAU IS THE ANSWER TO "WHICH STAGE SHOULD THE BENCHMARK USE".
# A stage whose duration barely moves while the account levels underneath it
# is a far better measurement target than one still climbing, because the
# progression drift documented below mostly cancels out there. Stages 4-6 all
# qualify; stage 4 is the cheapest to reach from the world map.
#
# NOTE: Garen Forest has SEVEN stages - the Elven Ranger reward text on the
# region screen says "Clear Garen Forest - Stage 7 (Normal) to obtain". So
# stage 7 is the last one here, and Next Stage after it will do something
# different: either the button is gone, or it points at a region that is still
# locked. Check the _12_menu frame after stage 7 before assuming --from 14
# still works.
#
# Waited per stage, because the stages are not remotely the same length. The
# wait is longer than the clock for stage 1 and shorter for stage 2 because
# the clock measures only the fight while the wait also has to cover the intro
# animation - and because overshooting is free. The victory screen waits for
# input indefinitely, so waiting too long costs a few seconds; waiting too
# little means the taps that follow land on a battle still in progress, which
# sends the whole cycle off the rails.
#
# DEFAULT_BATTLE_WAIT covers stages that have not been timed yet.
# Deliberately generous: an untimed stage is a later stage, and later stages
# are longer. Lower it once its TIME is known.
#
# THE SPREAD MATTERS AS MUCH AS THE LENGTH, and it moves in one direction.
# South was timed twice: 22.809s, then 16.127s a few battles later, a 29% drop
# with the same team on the same stage. It was flagged NEW BEST both times, so
# this is not random scatter - the monsters levelled up in between, hit harder,
# and finished in fewer turns.
#
# Two separate effects are stacked here and the report should keep them apart:
#   - RNG within a fixed team: crits, misses, turn order. Bounded scatter.
#   - Progression drift: the team strengthens monotonically, so the same
#     stage gets steadily cheaper. Not bounded, and not reversible.
#
# The second one is the awkward one for a benchmark. It means an energy figure
# for "Garen Forest stage 2" is only meaningful together with the monster
# levels it was recorded at, and that measurements taken weeks apart cannot be
# compared directly. That is a property of the game, not a flaw in the
# measurement, but it has to be stated or readers will read the trend as
# noise.
#
# Practically: the waits below need headroom over the SLOWEST observed time,
# not the typical one, because a fresh account fights slower than this one
# does now.
#
# For the energy work: stage 1 at ~4.5s is too short for batterystats, whose
# counters are coarse enough that its own noise would swamp the signal. Stage
# 2 at ~23s is a different proposition. Either batch N battles into one
# reset/dump window, or use a stage long enough to resolve on its own - which
# is what timing each stage as we advance is for.
# ---------------------------------------------------------------------
BATTLE_LOAD_WAIT = 12.0     # Start Battle -> battle actually on screen
BATTLE_WAIT_BY_STAGE = {
    1: 8.0,
    2: 20.0,
    3: 20.0,
    4: 30.0,
    5: 30.0,
    6: 30.0,
    7: 45.0,
}
# For stages not yet timed. Deliberately generous: undershooting is the
# expensive mistake - the taps that follow would hit a battle still in
# progress and derail the cycle - while overshooting just idles on a victory
# screen that waits for input forever anyway.
DEFAULT_BATTLE_WAIT = 45.0


def battle_wait_for(stage: int) -> float:
    """Seconds to wait for stage `stage` to finish fighting."""
    return BATTLE_WAIT_BY_STAGE.get(stage, DEFAULT_BATTLE_WAIT)
NEXT_STAGE_LOAD_WAIT = 6.0  # Next Stage -> team screen for that stage

# VICTORY SCREEN - measured from 80_auto_t008s.png. Dismissed by tapping any
# non-button area; this is empty grass on the left, far from every control.
#
# THE IN-GAME CLOCK IS FREE DATA. Top right reads TIME and BEST to the
# millisecond - the game measures the workload for us. Screenshotting it every
# run pairs the exact battle duration with that run's energy figure without
# timing anything from Python, which is what makes it possible to tell a noisy
# measurement apart from a battle that simply ran longer.
# ---------------------------------------------------------------------
# VICTORY SCREEN - measured from 80_auto_t008s.png
#
# THE IN-GAME CLOCK IS FREE DATA. Top right reads TIME and BEST to the
# millisecond - the game measures the workload for us. Screenshotting it every
# run pairs the exact battle duration with that run's energy figure without
# timing anything from Python, which is what makes it possible to tell a noisy
# measurement apart from a battle that simply ran longer.
#
# HOW MANY TAPS IT TAKES TO GET PAST THIS SCREEN VARIES. Normally one tap
# opens the chest. But the summoner levels up every so often, and a LEVEL UP
# banner then sits on top of the victory screen and swallows a tap of its own
# ("Energy MAX +2, Crystal +5" was the one seen at level 7). Monster level-ups
# behave the same way. Which battle triggers one is not predictable from the
# script's side.
#
# Handled by tapping the same empty spot several times instead of trying to
# work out how many popups there are. Tapping more than needed is free as long
# as the spot has no button on it.
#
# CHOOSING THE SPOT MATTERS MORE THAN THE COUNT. The obvious empty patch of
# grass at (0.250, 0.450) sits directly above the Replay button, whose top
# edge is around y=0.492 on the post-battle menu that appears once everything
# is cleared. A stray tap there starts another battle and spends 3 more
# energy. (0.100, 0.280) is the waterfall in the top left - empty on the
# victory screen, empty behind the level-up banner, and empty on the
# post-battle menu.
# ---------------------------------------------------------------------
VICTORY_DISMISS_FX, VICTORY_DISMISS_FY = 0.100, 0.280
VICTORY_TAPS = 6
VICTORY_TAP_GAP = 1.2
# After the last dismiss tap, before the item popup is expected. The chest
# animation runs here.
VICTORY_GAP = 4.0

# ---------------------------------------------------------------------
# CHEST AND DROP POPUP - measured from 91_after_victory_t03s.png
#
# The sequence after a win is:
#
#     VICTORY  ->  taps  ->  (LEVEL UP banner, sometimes)  ->  chest opens
#                                                                   |
#         post-battle menu  <---  OK  <---  item popup  <-----------+
#
# There is always a chest and always one item popup, and its OK button is in
# the middle of the screen - a different place from the empty spot used to
# clear the victory screen, which is why this is a separate tap rather than
# more of the same.
#
# One tap is enough here. The earlier confusion, where a popup was still on
# screen after tapping OK, was a timing problem: VICTORY_GAP was shorter than
# the chest animation, so OK fired before the popup existed.
# ---------------------------------------------------------------------
DROP_POPUP_OK_FX, DROP_POPUP_OK_FY = 0.503, 0.832
DROP_POPUP_CLOSE_FX, DROP_POPUP_CLOSE_FY = 0.654, 0.242   # the X, same effect
DROP_GAP = 3.0

# ---------------------------------------------------------------------
# POST-BATTLE MENU - measured from 96_after_drop_t03s.png
#
# Two big buttons (Replay / Next Stage, 3 energy each) and four icons along
# the bottom right. This is the screen the repeat loop will live on: Replay
# restarts the same stage without going back through the world map and stage
# list, cutting the loop to one tap and cutting the menu time folded into each
# battery measurement.
#
# Next Stage does NOT go straight into combat - it lands on that stage's TEAM
# SCREEN and still needs a Start Battle tap. Verified, after assuming
# otherwise and being wrong.
# ---------------------------------------------------------------------
REPLAY_FX, REPLAY_FY = 0.359, 0.545
NEXT_STAGE_FX, NEXT_STAGE_FY = 0.647, 0.545
PREPARE_FX, PREPARE_FY = 0.623, 0.813
WORLD_MAP_FX, WORLD_MAP_FY = 0.715, 0.813
RETURN_FX, RETURN_FY = 0.807, 0.813
RUNES_FX, RUNES_FY = 0.898, 0.813

# ---------------------------------------------------------------------
# THE RIGHT-HAND BUTTON CHANGES MEANING ON THE LAST STAGE
#
# Measured from 80_adv6_12_menu.png. After clearing stage 7 (Hollows), the
# slot that says "Next Stage 3" on every other stage says "Quit" instead -
# same position, same size, no energy cost, completely different action.
# There is no stage 8 in Garen Forest, so there is nothing to advance to.
#
# The coordinates are therefore identical and the constant is a second name
# for the same point, kept separate so call sites read as what they mean.
#
# THIS IS THE SHARPEST EXAMPLE YET OF WHY COORDINATES ARE NOT ENOUGH. Every
# other drift so far changed how many times to tap or how long to wait. This
# one changes what a tap DOES, while looking identical to the script. Tapping
# "Next Stage" on stage 7 quits; tapping "Quit" on stage 3 spends 3 energy and
# starts a battle the script is not expecting. A position alone carries no
# information about which of those is under the finger - only the label does,
# and reading labels is exactly what the model-driven phase is for.
#
# Guarded here by arithmetic rather than by reading the screen: the script
# knows which stage it just fought, so it can work out whether that was the
# last one. That works only because the region size is known and hardcoded,
# which is the same brittleness in a new place.
# ---------------------------------------------------------------------
QUIT_FX, QUIT_FY = 0.647, 0.545          # same slot as Next Stage
LAST_STAGE_IN_REGION = 7                 # Garen Forest ends at stage 7

# How many stages step 14 advances through in one go, on top of the stage
# fought in step 13. Each costs 3 energy and permanently advances progress.
#
# 6 sweeps a full cold run through the whole region: step 13 fights stage 1,
# then step 14 advances 2, 3, 4, 5, 6, 7. That is 7 battles, 21 energy, and
# roughly 8 minutes.
#
# Set it to 1 when working out the timing for a single new stage, so a mistake
# costs one battle instead of six.
#
# Careful about reading across a long sweep: monsters level as it runs, so the
# team at stage 7 is not the team that fought stage 1, and the durations are
# not strictly comparable with each other. Fine for finding the plateau,
# misleading if treated as a controlled comparison.
STAGES_TO_ADVANCE = 6

# ---------------------------------------------------------------------
# DO NOT TAP - recorded so nobody adds them later thinking they were missed
#
# The "additional download is required" bar has a Collect button under it. It
# said 773.93MB when first measured and says 2102.40MB now. Tapping it starts
# a multi-GB download that would dominate any energy measurement taken
# afterwards and change the install for every later run.
#
# The Level dropdown (Normal / Hard / Hell) on the stage panel changes the
# workload - different monster stats, different battle length, different
# energy cost. Normal is the default and stays the default.
#
# The x2 XP and x2 crystal badges on the victory screen are reward-doubling
# offers. They cost crystals or trigger an ad, either of which spends account
# resources and fires network traffic in the middle of a measurement.
# ---------------------------------------------------------------------
DOWNLOAD_COLLECT_FX, DOWNLOAD_COLLECT_FY = 0.503, 0.126   # NEVER tap this
LEVEL_DROPDOWN_FX, LEVEL_DROPDOWN_FY = 0.845, 0.190       # NEVER tap this
VICTORY_XP_X2_FX, VICTORY_XP_X2_FY = 0.831, 0.320         # NEVER tap this
VICTORY_GEM_X2_FX, VICTORY_GEM_X2_FY = 0.902, 0.320       # NEVER tap this
# The Buy buttons on the special offer panel open a real payment flow. Not
# recorded as coordinates at all - there is no use for them and no reason to
# have the numbers lying around where a typo could reach them.

# TODO (deferred, not forgotten): idle baseline. Sit on the hub for a fixed
# window with zero taps and record batterystats. More important than it looked
# earlier: with stage 1 only 4.5s long, most of a repeat window is menu
# navigation, and the baseline is what allows that share to be subtracted out
# rather than reported as if it were combat.
#
# TODO: batterystats reset at the top of run_battle_cycle, dump at the bottom
# - or around a whole batch of cycles if one battle stays too short to
# resolve.


def parse_int_arg(argv, flag: str, default: int) -> int:
    """Read `flag N` off the command line, e.g. `--from 14` or `--stage 2`.

    Deliberately tiny instead of argparse: the only things that ever need
    parsing here are two integers.
    """
    if flag not in argv:
        return default
    i = argv.index(flag)
    if i + 1 >= len(argv):
        print(f"{flag} needs a number, e.g. {flag} 2")
        sys.exit(1)
    try:
        return int(argv[i + 1])
    except ValueError:
        print(f"{flag} expects a number, got {argv[i + 1]!r}")
        sys.exit(1)


def run_battle_cycle(c: AdbController, tag: str, stage: int):
    """Fight one battle, starting and ending on a known screen.

    ENTRY:  the TEAM SCREEN (the VS layout with Start Battle on the right).
    EXIT:   the POST-BATTLE MENU (Replay / Next Stage).

    Both ends are stable screens that wait for input indefinitely, which is
    what makes this safe to call in a loop - there is no timing dependency
    between one cycle and the next.

    `stage` picks how long to wait for the fighting to finish, from
    BATTLE_WAIT_BY_STAGE. It is passed in rather than detected, because the
    script has no way to read which stage it is on.

    Every screenshot is prefixed with `tag` so cycles do not overwrite each
    other's frames.

    Costs 3 energy per call and cannot be undone.
    """
    wait = battle_wait_for(stage)
    print(f"  [{tag}] stage {stage}: team screen -> Start Battle "
          f"(battle wait {wait:.0f}s)")
    # Capture the team BEFORE fighting. Composition and levels are the record
    # of what the workload was for this particular battle - and they change on
    # their own, so a screenshot per cycle is the only way to know afterwards.
    c.take_screenshot(f"{tag}_00_team.png")
    c.tap_frac(START_BATTLE_FX, START_BATTLE_FY)

    time.sleep(BATTLE_LOAD_WAIT)
    c.take_screenshot(f"{tag}_01_battle.png")

    # Only on the first battle after launching the app - see the AUTO RESETS
    # comment. Tapping this when auto is already on would switch it off.
    global NEEDS_AUTO_TAP
    if NEEDS_AUTO_TAP:
        print(f"  [{tag}] first battle since launch - enabling auto")
        c.tap_frac(BATTLE_AUTO_FX, BATTLE_AUTO_FY)
        NEEDS_AUTO_TAP = False
        time.sleep(2.0)
    else:
        print(f"  [{tag}] auto already on for this session")

    # Let the battle play itself out. Length depends on the stage.
    time.sleep(wait)

    # Victory. Keep this frame: it carries the in-game battle clock and the
    # post-battle monster levels.
    c.take_screenshot(f"{tag}_10_victory.png")

    # Several taps on the same empty spot, because a level-up banner sometimes
    # sits between the victory screen and the chest and eats one of them. The
    # spot has no button on it in any of those screens, so overshooting costs
    # nothing. See the VICTORY SCREEN comment for why the spot moved.
    print(f"  [{tag}] clearing victory ({VICTORY_TAPS} taps)")
    for _ in range(VICTORY_TAPS):
        c.tap_frac(VICTORY_DISMISS_FX, VICTORY_DISMISS_FY)
        time.sleep(VICTORY_TAP_GAP)

    # Chest animation, then the item popup and its OK button in the middle.
    time.sleep(VICTORY_GAP)
    print(f"  [{tag}] item popup -> OK")
    c.take_screenshot(f"{tag}_11_drop.png")
    c.tap_frac(DROP_POPUP_OK_FX, DROP_POPUP_OK_FY)
    time.sleep(DROP_GAP)

    c.take_screenshot(f"{tag}_12_menu.png")

    print(f"  [{tag}] done - should be on the post-battle menu")


if __name__ == "__main__":
    controller = AdbController()
    START = parse_int_arg(sys.argv, "--from", 1)
    # Which stage the FIRST battle of this run fights. Only affects how long
    # the script waits for that battle; step 14 counts up from here for each
    # stage it advances through.
    STAGE = parse_int_arg(sys.argv, "--stage", 1)

    print("=== Step 1: Checking device connection ===")
    if not controller.check_connection():
        print("No device detected! Make sure the emulator is running and "
              "adb is configured correctly.")
        sys.exit(1)

    # --find mode: just list candidate packages and stop.
    if "--find" in sys.argv:
        print("\n=== Looking for the game's package name ===")
        for keyword in ("sky", "arena"):
            print(f"\npackages containing {keyword!r}:")
            controller.list_packages(keyword)
        print("\nIf nothing above looks right, list everything with:")
        print("    adb shell pm list packages -3")
        print("(-3 = third-party apps only, i.e. things you installed)")
        sys.exit(0)

    if START > 1:
        print(f"\n*** --from {START}: skipping steps 2..{START - 1}. ***")
        print("*** The game must ALREADY be showing what step "
              f"{START} expects. ***")

    if START <= 2:
        print("\n=== Step 2: Screen size ===")
        controller.screen_size()

    if START <= 3:
        print("\n=== Step 3: Opening Sky Arena ===")
        controller.open_app(SKY_ARENA_PACKAGE)
        # A freshly launched game has auto-battle off. The first battle cycle
        # of this run has to switch it on; every later one must not touch it.
        NEEDS_AUTO_TAP = True
    else:
        # The game has been open since an earlier invocation, so auto is
        # already on and tapping the toggle would switch it off.
        print("  (game already running - auto assumed on, toggle left alone)")

    if START <= 4:
        print(f"\n=== Step 4: First screenshot (after {LAUNCH_WAIT}s) ===")
        time.sleep(LAUNCH_WAIT)
        controller.take_screenshot("01_launch.png")
        controller.current_activity()

    if START <= 5:
        print("\n=== Step 5: Boot sequence ===")
        elapsed = LAUNCH_WAIT
        for i in range(1, SETTLE_SHOTS + 1):
            time.sleep(SETTLE_WAIT)
            elapsed += SETTLE_WAIT
            print(f"  t = {elapsed}s")
            controller.take_screenshot(f"0{i + 1}_t{elapsed}s.png")

    # OUTSIDE the step guards on purpose. Every tap_frac below needs
    # fb_w/fb_h, so this has to run no matter which step we enter at. If it
    # somehow reads portrait, tap_frac raises instead of tapping blind.
    print("\n=== Measuring framebuffer ===")
    controller.framebuffer_size()

    if START <= 6:
        print("\n=== Step 6: Dismissing the promo banners ===")
        for i in range(1, POPUP_COUNT + 1):
            controller.take_screenshot(f"10_popup_{i}_before.png")
            print(f"  closing banner {i}")
            controller.tap_frac(POPUP_CLOSE_FX, POPUP_CLOSE_FY)
            time.sleep(POPUP_TAP_GAP)
            controller.take_screenshot(f"11_popup_{i}_after.png")

    if START <= 7:
        print("\n=== Step 7: Touch to Start ===")
        controller.take_screenshot("19_title_screen.png")
        controller.tap_frac(TOUCH_TO_START_FX, TOUCH_TO_START_FY)
        time.sleep(15)
        controller.take_screenshot("20_after_touch_to_start.png")

    if START <= 8:
        print("\n=== Step 8: Clearing the login panels ===")
        # Alternating passes because the order the two panels open in is not
        # fixed - see the LOGIN PANELS comment. Screenshot before each round
        # so which panel was actually on top is recoverable afterwards.
        for r in range(1, LOGIN_PANEL_ROUNDS + 1):
            controller.take_screenshot(f"30_login_panels_r{r}.png")
            print(f"  round {r}: offer panel X")
            controller.tap_frac(SHOP_POPUP_CLOSE_FX, SHOP_POPUP_CLOSE_FY)
            time.sleep(LOGIN_PANEL_GAP)
            print(f"  round {r}: gift box X")
            controller.tap_frac(GIFT_BOX_CLOSE_FX, GIFT_BOX_CLOSE_FY)
            time.sleep(LOGIN_PANEL_GAP)
        controller.take_screenshot("31_after_login_panels.png")

    if START <= 9:
        print("\n=== Step 9: Settling on the hub ===")
        for i in range(1, POST_LOGIN_SHOTS + 1):
            time.sleep(POST_LOGIN_GAP)
            controller.take_screenshot(f"3{i + 1}_hub_t{int(i * POST_LOGIN_GAP)}s.png")

    if START <= 10:
        print("\n=== Step 10: Opening the Battle menu ===")
        controller.tap_frac(BATTLE_FX, BATTLE_FY)
        time.sleep(4.0)
        controller.take_screenshot("40_battle_menu.png")
        time.sleep(4.0)
        controller.take_screenshot("41_battle_menu_settled.png")

    if START <= 11:
        print("\n=== Step 11: Entering Garen Forest ===")
        controller.tap_frac(GAREN_FOREST_FX, GAREN_FOREST_FY)
        time.sleep(4.0)
        controller.take_screenshot("50_garen_forest.png")
        time.sleep(4.0)
        controller.take_screenshot("51_garen_forest_settled.png")

    if START <= 12:
        print("\n=== Step 12: Stage 1 Outskirts -> team screen ===")
        controller.tap_frac(STAGE1_BATTLE_FX, STAGE1_BATTLE_FY)
        time.sleep(4.0)
        controller.take_screenshot("60_stage1_battle.png")
        time.sleep(4.0)
        controller.take_screenshot("61_stage1_battle_settled.png")

    if START <= 13:
        print("\n=== Step 13: One battle cycle ===")
        # Entry is the team screen, exit is the post-battle menu. Costs 3
        # energy.
        run_battle_cycle(controller, "70_cycle1", STAGE)

    if START <= 14:
        print(f"\n=== Step 14: Advancing {STAGES_TO_ADVANCE} stage(s) ===")
        # Next Stage lands on the NEXT stage's team screen - it does not go
        # straight into combat, which is why run_battle_cycle follows rather
        # than the battle being watched directly.
        #
        # The stage number counts up so each battle gets the right wait. A
        # stage with no measured time falls back to DEFAULT_BATTLE_WAIT.
        #
        # Each iteration permanently advances progress and spends 3 energy.
        for n in range(1, STAGES_TO_ADVANCE + 1):
            next_stage = STAGE + n
            print(f"\n  --- advancing to stage {next_stage} "
                  f"({n}/{STAGES_TO_ADVANCE}) ---")
            controller.take_screenshot(f"80_adv{n}_00_menu.png")
            controller.tap_frac(NEXT_STAGE_FX, NEXT_STAGE_FY)
            time.sleep(NEXT_STAGE_LOAD_WAIT)
            run_battle_cycle(controller, f"80_adv{n}", next_stage)

    if START <= 15:
        final_stage = STAGE + STAGES_TO_ADVANCE
        print(f"\n=== Step 15: Quit (last fought stage was {final_stage}) ===")
        # Only safe when the stage just cleared really was the last one in the
        # region. On any earlier stage that same point is Next Stage, and
        # tapping it would spend 3 energy on a battle nothing is waiting for.
        if final_stage >= LAST_STAGE_IN_REGION:
            controller.take_screenshot("90_last_menu.png")
            print("  tapping Quit")
            controller.tap_frac(QUIT_FX, QUIT_FY)
            time.sleep(5.0)
            controller.take_screenshot("91_after_quit.png")
        else:
            print(f"  skipped - stage {final_stage} is not the last in the "
                  f"region (last is {LAST_STAGE_IN_REGION}), so that slot is "
                  "still Next Stage and tapping it would start a battle")
    print("\nDone. Send the *_10_victory.png frames - one per cycle.")
    print("Battle durations measured so far:")
    print("    stage 1 Outskirts : 00:04.472              -> wait 8s")
    print("    stage 2 South     : 00:22.809 / 00:16.127  -> wait 20s")
    print("    stage 3 East      : 00:19.377              -> wait 20s")
    print("    stage 4 Paths     : 00:27.061              -> wait 30s")
    print("    stage 5           : 00:27.126              -> wait 30s")
    print("    stage 6 Plateau   : 00:28.217              -> wait 30s")
    print("    stage 7 Hollows   : 00:29.827              -> wait 45s")
    print("Stages 4-7 sit inside a 2.8s band - that plateau is where the")
    print("benchmark stage should come from.")
    print("\nIf a _10_victory.png still shows combat, the wait for that stage")
    print("is too short and everything after it tapped the wrong screen.")
    print("\nNext runs:")
    print("    --from 14 --stage N   N is the stage just FOUGHT; the script")
    print("                          advances to N+1 and waits accordingly")
    print("    --from 13 --stage N   refight stage N from its team screen")