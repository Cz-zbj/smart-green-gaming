"""
tcgp_adb_controller.py

Bootstrap script for Pokemon TCG Pocket, same "hands" module pattern as
raid_adb_controller.py / sky_arena_adb_controller.py / adb_controller.py
(Flow Free) - AdbController is copy-pasted unchanged.

This is a BOOTSTRAP script, not the full automation. It only covers what can
be done before any screen has been measured: find the package, launch it,
wait, screenshot, confirm what's in the foreground. Once screenshots come
back, we measure coordinates from them and extend the script step by step,
same as every other game so far.

USAGE
    python tcgp_adb_controller.py --find                 list candidate packages
    python tcgp_adb_controller.py --package <name>        open + screenshot
    python tcgp_adb_controller.py --package <name> --wait 60   longer launch wait
"""

import subprocess
import time
import os
import sys


class AdbController:
    def __init__(self, device_id: str = None, screenshot_dir: str = "screenshots_tcgp"):
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
        """Raw uiautomator accessibility tree dump. If the UI is drawn
        inside a Unity/Canvas surface, this comes back basically empty -
        that tells us coordinates are the only option, same conclusion
        every other game here reached."""
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

    def _fingerprint(self, path):
        """Downscale to 32x32 greyscale. Small enough that an animated
        background (sparkle effects, card-shine loops) averages out, big
        enough that a real screen change is obvious. Returns None if
        Pillow isn't installed."""
        try:
            from PIL import Image
        except ImportError:
            return None
        with Image.open(path) as im:
            return list(im.convert("L").resize((32, 32)).getdata())

    def screens_differ(self, path_a, path_b, threshold=6.0):
        """True if these two screenshots show a different screen (not
        just animation noise). None if Pillow is missing - caller
        decides what to do."""
        fa, fb = self._fingerprint(path_a), self._fingerprint(path_b)
        if fa is None or fb is None:
            return None
        diff = sum(abs(a - b) for a, b in zip(fa, fb)) / len(fa)
        print(f"  screen difference: {diff:.2f} (threshold {threshold})")
        return diff > threshold

    def press_back(self):
        """Android BACK key. Coordinate-free, so it works on overlays
        whose dismiss position we haven't measured - and unlike tapping a
        guessed spot, it can't accidentally land on something else and
        navigate somewhere unintended."""
        print("Pressing BACK")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "keyevent", "4"],
            check=True,
        )

    def force_stop(self, package_name: str):
        """Close the game. Ends every run on a known state."""
        print(f"Force-stopping {package_name}")
        subprocess.run(
            self._adb_prefix() + ["shell", "am", "force-stop", package_name],
            check=True,
        )

    def framebuffer_size(self):
        """Actual width/height of what screencap produces, read straight
        from the PNG header. MUST be called while the screen is showing
        what you intend to measure - calling it too early records the
        wrong orientation, and that failure is silent: taps dispatch, adb
        exits 0, nothing on screen reacts."""
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

    def tap(self, x: int, y: int):
        print(f"Tapping at: ({x}, {y})")
        subprocess.run(
            self._adb_prefix() + ["shell", "input", "touchscreen", "tap", str(x), str(y)],
            check=True,
        )

    def tap_frac(self, fx: float, fy: float):
        """Tap a point given as a fraction of the framebuffer, e.g.
        (0.5, 0.5) is dead centre. Fractions instead of pixels so
        coordinates survive a different emulator resolution."""
        if getattr(self, "fb_w", None) is None:
            raise RuntimeError("call framebuffer_size() first")
        x = int(round(fx * self.fb_w))
        y = int(round(fy * self.fb_h))
        print(f"  frac ({fx:.3f}, {fy:.3f}) -> px ({x}, {y})")
        self.tap(x, y)


# Confirmed via --find.
TCGP_PACKAGE = "jp.pokemon.pokemontcgp"

LAUNCH_WAIT = 15.0   # seconds to wait after launch before screenshotting

# ---------------------------------------------------------------------
# TITLE SCREEN - measured from 01_launch.png (1080x2400 framebuffer,
# PORTRAIT - unlike Raid/Sky Arena, so no landscape check needed here).
# Shows a "tap anywhere to start" prompt near the bottom. Not a specific
# button, so any empty spot works - using the prompt text's own position,
# clear of the floating card art scattered around the rest of the screen.
# ---------------------------------------------------------------------
TITLE_TAP_FX, TITLE_TAP_FY = 0.500, 0.865
TITLE_TAP_SETTLE_WAIT = 3.0
# How long to wait after the first tap before the second one. The pack-
# ready banner takes a moment to load in after the game screen appears -
# tapping too soon (previously only 3s) landed on whatever was still
# mid-transition instead of the settled banner, which is why the earlier
# attempt opened the pack screen instead of dismissing it.
PACK_BANNER_WAIT = 5.0

# ---------------------------------------------------------------------
# HOME SCREEN BOTTOM NAV BAR - re-measured from 04_battle_menu_settled.png
# (1080x2400, clean shot, no overlay in the way). Five icons, evenly
# spaced at roughly x = 140/340/540/740/942px: Home, Deck, Friends,
# Battle (4th - has a red notification badge), Menu.
#
# Earlier measurement (from a screenshot with a banner still blurring the
# bar) put Battle at fx=0.694 - close, but tapping it landed on the
# booster-pack screen instead of the battle menu. This pass reads the
# icons cleanly instead of guessing through the blur.
# ---------------------------------------------------------------------
NAV_HOME_FX = 0.130
NAV_DECK_FX = 0.315
NAV_FRIENDS_FX = 0.500
NAV_BATTLE_FX = 0.685   # 4th icon - has the red badge, used to enter Versus
NAV_MENU_FX = 0.872
NAV_BAR_FY = 0.979
NAV_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# BATTLE MENU - measured from 04_battle_menu.png (1080x2400). Two big
# cards under the banner: "Versus others" (left, has a "closing soon"
# tag under it) and "Single player" (right). Single player is the one
# needed - it doesn't depend on matchmaking or another live opponent.
# ---------------------------------------------------------------------
SINGLE_PLAYER_FX, SINGLE_PLAYER_FY = 0.741, 0.800
SINGLE_PLAYER_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# SINGLE PLAYER SUB-MENU - measured from 05_single_player_settled.png
# (1080x2400). Two cards: "Casual" (left) and "Ranked" (right, has the
# staircase icon). Same row position as the Battle menu's own two cards,
# just one screen deeper.
# ---------------------------------------------------------------------
RANKED_FX, RANKED_FY = 0.738, 0.793
RANKED_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# RANKED TIER LIST - measured from 06_ranked_settled.png (1080x2400).
# Three tiers stacked vertically, each its own card: Beginner (top,
# orange bar), Intermediate (middle, blue bar), Advanced (bottom, dark
# bar). Tapping the orange "Beginner" bar on the first card.
# ---------------------------------------------------------------------
TIER_BEGINNER_FX, TIER_BEGINNER_FY = 0.500, 0.327
TIER_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# BEGINNER TIER OPPONENT LIST - measured from 07_beginner_settled.png
# (1080x2400). One AI deck card shown ("Team Rocket's Bidoof deck" from
# the Team Rocket's Ambition set), tagged "AI". Tapping this card opens
# a deck detail page.
#
# NOTE: this list is NOT static. After clearing a deck once (2/2 shown
# with a checkmark), a second AI deck unlocks below it - and the FIRST
# card's position shifts up to make room (fy 0.588 -> 0.508, re-measured
# from a screenshot taken after the first win). More wins will likely
# keep changing this list's shape, so re-check fy here if a fresh
# screenshot shows the card sitting somewhere else.
# ---------------------------------------------------------------------
# NOTE: this list keeps changing shape - clearing a deck unlocks the
# next one below it, and every card above shifts up to make room. Each
# fy below was re-measured against the latest screenshot showing all
# three decks unlocked so far; if a fourth one appears, re-check all
# three again rather than assuming they hold still.
DECK_CARD_FX, DECK_CARD_FY = 0.500, 0.422

# Second AI deck on this same list ("Team Rocket's Mr. Mime deck").
DECK_CARD_2_FX, DECK_CARD_2_FY = 0.500, 0.590

# Third AI deck ("Team Rocket's Zorua deck"), unlocked after clearing
# the second one.
DECK_CARD_3_FX, DECK_CARD_3_FY = 0.500, 0.756

# Gap after returning to this list (post-Continue) before tapping into
# the next deck - the checkmark/unlock state needs a moment to refresh.
BETWEEN_MATCHES_WAIT = 10.0
DECK_DETAIL_LOAD_WAIT = 4.0

# ---------------------------------------------------------------------
# DECK DETAIL PAGE - measured from phone_shot.png (1080x2400, manual
# screenshot - the earlier automated one fired before this page finished
# loading, since that step skipped the settle wait). Shows the deck,
# first-clear rewards, battle challenges, a recommended opponent deck
# card, a big "Battle!" button, an X to back out, and an "Auto OFF"
# toggle bottom-right.
# ---------------------------------------------------------------------
START_BATTLE_FX, START_BATTLE_FY = 0.500, 0.882
AUTO_TOGGLE_FX, AUTO_TOGGLE_FY = 0.787, 0.952
BATTLE_TAP_LOAD_WAIT = 10.0

# ---------------------------------------------------------------------
# MATCH SCREEN - measured from a second phone_shot.png (1080x2400),
# taken after Battle! loaded into the actual match. Has its own "Auto"
# toggle near the top right (separate control from the deck-detail
# page's "Auto OFF" pill measured above - different screen, different
# position). Turning it on lets the AI opponent's turn (and the coin-
# flip / mulligan animations) play out without manual taps.
#
# Wait floor after enabling Auto is a guess (2:30) for one full early
# match to finish - no in-game timer to calibrate against yet, unlike
# Raid's Best Times. Revisit once a real match duration is observed.
# ---------------------------------------------------------------------
MATCH_AUTO_TOGGLE_FX, MATCH_AUTO_TOGGLE_FY = 0.884, 0.267
# Extra settle time between the post-Battle! screenshot and tapping
# Auto - the match screen takes a moment longer to become interactive
# than the load wait alone accounts for.
PRE_AUTO_TAP_WAIT = 5.0

# ---------------------------------------------------------------------
# POST-MATCH SCREENS - measured from 10_after_auto_wait.png and a
# second phone_shot.png (both 1080x2400). After the match ends there
# are a few "tap anywhere to continue" screens in a row (win banner,
# card reveal, VS-recap) before a real button shows up - "Continue" on
# the VS-recap screen, which needs its own coordinate since it's an
# actual button, not a tap-anywhere prompt.
#
# WIN_TAP is a generic point safe to use on any of the tap-anywhere
# screens. (0.5, 0.5) - dead centre - looked safe on the card-reveal
# screen but lands directly on the "standout card" artwork on the VS-
# recap screen instead, which the game treats as "inspect this card"
# rather than "continue", stalling the tap-through. Moved to the top
# strip instead: empty gradient background on every post-match screen
# seen so far (card reveal, VS recap), clear of the avatar icon that
# sits a bit further down on both.
WIN_TAP_FX, WIN_TAP_FY = 0.500, 0.040
WIN_TAP_COUNT = 3
CONTINUE_FX, CONTINUE_FY = 0.500, 0.952


def parse_float_arg(argv, flag: str, default: float) -> float:
    if flag not in argv:
        return default
    i = argv.index(flag)
    if i + 1 >= len(argv):
        print(f"{flag} needs a number")
        sys.exit(1)
    return float(argv[i + 1])


def parse_str_arg(argv, flag: str, default):
    if flag not in argv:
        return default
    i = argv.index(flag)
    if i + 1 >= len(argv):
        print(f"{flag} needs a value")
        sys.exit(1)
    return argv[i + 1]


def wait_until_stable(controller: AdbController, tag: str,
                      poll_gap: float = 3.0, timeout: float = 300.0,
                      stable_needed: int = 3) -> float:
    """Screenshot every poll_gap seconds until the screen has looked the
    same `stable_needed` times IN A ROW - not just once.

    Requiring only one match is too easy to trigger by accident: a live
    match can sit still for a few seconds between turns (the opponent
    "thinking", an animation finishing) and that alone was getting
    mistaken for the match being over - which then fired the post-match
    taps INTO an ongoing match, on a real board, instead of onto the
    actual win screen. Demanding several consecutive stable checks
    (stable_needed x poll_gap seconds of true silence) filters that out,
    same fix Raid's battle-wait used (BATTLE_POLL_STABLE_NEEDED).

    Replaces guessing a fixed wait for a variable-length match. `timeout`
    is a safety net in case something never settles (a connection
    hiccup, an unexpected dialog) - it stops polling rather than looping
    forever, but does NOT mean the wait succeeded.

    Returns how many seconds were spent waiting.
    """
    prev = controller.take_screenshot(f"{tag}_wait00.png")
    waited = 0.0
    stable = 0
    i = 0
    while waited < timeout:
        time.sleep(poll_gap)
        waited += poll_gap
        i += 1
        cur = controller.take_screenshot(f"{tag}_wait{i:02d}.png")
        differs = controller.screens_differ(prev, cur)
        if differs is None:
            print("  Pillow not installed - can't detect when the "
                  "screen settles. Install with: pip install pillow")
            return waited
        stable = 0 if differs else stable + 1
        prev = cur
        if stable >= stable_needed:
            print(f"  [{tag}] screen settled after {waited:.0f}s "
                  f"({stable_needed} consecutive stable checks)")
            return waited
    print(f"  [{tag}] still changing after {timeout:.0f}s - giving up "
          "and continuing anyway, check the wait frames")
    return waited


def tap_through_when_stable(controller: AdbController, tag: str,
                            fx: float, fy: float, times: int,
                            poll_gap: float = 3.0,
                            timeout: float = 30.0,
                            stable_needed: int = 3) -> None:
    """Tap `times` times, but only once the screen has actually stopped
    changing before each tap - not on a fixed gap, and not on a single
    lucky stable check either (see wait_until_stable). Covers the run of
    "tap anywhere to continue" screens after a match (win banner, card
    reveal, VS recap): each one needs its animation to finish before the
    tap registers as advancing rather than getting swallowed mid-
    transition, and how long that takes isn't constant.
    """
    for n in range(1, times + 1):
        wait_until_stable(controller, f"{tag}_tap{n}", poll_gap, timeout,
                          stable_needed)
        controller.tap_frac(fx, fy)
        controller.take_screenshot(f"{tag}_after_tap{n:02d}.png")


def play_one_match(controller: AdbController, tag: str,
                   deck_fx: float, deck_fy: float) -> None:
    """One full cycle: tap an AI deck card on the opponent list, start
    the battle, turn Auto on, wait out the match, tap through the
    post-match screens, and hit Continue - landing back on the opponent
    list. `tag` prefixes every screenshot from this cycle so two calls
    (e.g. one per deck) don't overwrite each other's files.
    """
    print(f"\n=== [{tag}] Tapping the AI deck card ===")
    controller.tap_frac(deck_fx, deck_fy)
    time.sleep(DECK_DETAIL_LOAD_WAIT)
    controller.take_screenshot(f"{tag}_00_deck.png")

    print(f"\n=== [{tag}] Tapping Battle! ===")
    controller.tap_frac(START_BATTLE_FX, START_BATTLE_FY)
    time.sleep(BATTLE_TAP_LOAD_WAIT)
    controller.take_screenshot(f"{tag}_01_battle_tap.png")

    print(f"\n=== [{tag}] Tapping Auto, then waiting for the match to "
          "settle (polling, not a fixed wait) ===")
    time.sleep(PRE_AUTO_TAP_WAIT)
    controller.tap_frac(MATCH_AUTO_TOGGLE_FX, MATCH_AUTO_TOGGLE_FY)
    wait_until_stable(controller, f"{tag}_02", poll_gap=3.0, timeout=300.0)
    controller.take_screenshot(f"{tag}_02_after_auto_wait.png")

    print(f"\n=== [{tag}] Tapping through the post-match screens "
          "(waiting for each to settle before tapping) ===")
    tap_through_when_stable(controller, f"{tag}_03", WIN_TAP_FX,
                            WIN_TAP_FY, WIN_TAP_COUNT, poll_gap=3.0,
                            timeout=30.0)

    print(f"\n=== [{tag}] Tapping Continue ===")
    controller.tap_frac(CONTINUE_FX, CONTINUE_FY)
    controller.take_screenshot(f"{tag}_04_after_continue.png")


if __name__ == "__main__":
    device_id = parse_str_arg(sys.argv, "--device", None)
    controller = AdbController(device_id=device_id)

    print("=== Checking device connection ===")
    if not controller.check_connection():
        print("No device detected! Make sure the emulator/device is "
              "running and adb is configured correctly.")
        sys.exit(1)
    if device_id is None:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        lines = [l for l in (result.stdout or "").strip().split("\n")[1:]
                 if l.strip()]
        if len(lines) > 1:
            print("\nMore than one device/emulator connected - adb "
                  "can't guess which one to use. Pick one with "
                  "--device <id>, e.g.:")
            for l in lines:
                dev_id = l.split()[0]
                print(f"    python {os.path.basename(__file__)} "
                      f"--device {dev_id}")
            print("(a phone with both USB and WiFi ADB active shows up "
                  "as two entries here - pick either one, or disconnect "
                  "one side.)")
            sys.exit(1)

    if "--find" in sys.argv:
        print("\n=== Searching installed packages for Pokemon TCG Pocket ===")
        print("\n-- keyword 'pokemon' --")
        controller.list_packages("pokemon")
        print("\n-- keyword 'pokemontcg' --")
        controller.list_packages("pokemontcg")
        print("\n-- keyword 'dena' (DeNA co-developed this game) --")
        controller.list_packages("dena")
        print("\nIf none of the above look right, run:")
        print("    adb shell pm list packages -3")
        print("and look for the correct one by hand (third-party packages "
              "only, filters out system apps).")
        sys.exit(0)

    if "--package" in sys.argv:
        i = sys.argv.index("--package")
        if i + 1 >= len(sys.argv):
            print("--package needs a value")
            sys.exit(1)
        package = sys.argv[i + 1]
    else:
        # Confirmed package - no need to pass --package every time.
        package = TCGP_PACKAGE

    launch_wait = parse_float_arg(sys.argv, "--wait", LAUNCH_WAIT)

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
                  "accessible nodes. Coordinates it is.")
        sys.exit(0)

    print(f"\n=== Step 1: Opening {package} ===")
    controller.open_app(package)

    print(f"\n=== Waiting {launch_wait:.0f}s for launch ===")
    time.sleep(launch_wait)

    print("\n=== Confirming foreground activity ===")
    controller.current_activity()

    print("\n=== Measuring framebuffer (game must be on screen) ===")
    controller.framebuffer_size()

    print("\n=== Screenshot ===")
    controller.take_screenshot("01_launch.png")

    print("\n=== Step 2: Tapping title screen to start (tap-to-start "
          "prompt) ===")
    controller.tap_frac(TITLE_TAP_FX, TITLE_TAP_FY)
    time.sleep(TITLE_TAP_SETTLE_WAIT)
    controller.take_screenshot("02_after_tap.png")

    print("\n=== Step 3: Waiting for the pack-ready banner to settle, "
          "then tapping the same spot again to dismiss it ===")
    time.sleep(PACK_BANNER_WAIT)
    controller.tap_frac(TITLE_TAP_FX, TITLE_TAP_FY)
    time.sleep(TITLE_TAP_SETTLE_WAIT)
    controller.take_screenshot("03_home.png")

    print("\n=== Step 4: Tapping bottom nav bar's 4th icon (Battle, has "
          "the red badge) ===")
    controller.tap_frac(NAV_BATTLE_FX, NAV_BAR_FY)
    time.sleep(NAV_LOAD_WAIT)
    controller.take_screenshot("04_battle_menu.png")
    time.sleep(NAV_LOAD_WAIT)
    controller.take_screenshot("04_battle_menu_settled.png")

    print("\n=== Step 5: Tapping Single Player battle card ===")
    controller.tap_frac(SINGLE_PLAYER_FX, SINGLE_PLAYER_FY)
    time.sleep(SINGLE_PLAYER_LOAD_WAIT)
    controller.take_screenshot("05_single_player.png")
    time.sleep(SINGLE_PLAYER_LOAD_WAIT)
    controller.take_screenshot("05_single_player_settled.png")

    print("\n=== Step 6: Tapping Ranked battle card ===")
    controller.tap_frac(RANKED_FX, RANKED_FY)
    time.sleep(RANKED_LOAD_WAIT)
    controller.take_screenshot("06_ranked.png")
    time.sleep(RANKED_LOAD_WAIT)
    controller.take_screenshot("06_ranked_settled.png")

    print("\n=== Step 7: Tapping the Beginner tier bar ===")
    controller.tap_frac(TIER_BEGINNER_FX, TIER_BEGINNER_FY)
    time.sleep(TIER_LOAD_WAIT)
    controller.take_screenshot("07_beginner.png")
    time.sleep(TIER_LOAD_WAIT)
    controller.take_screenshot("07_beginner_settled.png")

    print("\n=== Step 8: Playing the first AI deck ===")
    play_one_match(controller, "08_match1", DECK_CARD_FX, DECK_CARD_FY)

    print(f"\n=== Step 9: Waiting {BETWEEN_MATCHES_WAIT:.0f}s before the "
          "second deck ===")
    time.sleep(BETWEEN_MATCHES_WAIT)
    controller.take_screenshot("09_before_match2.png")

    print("\n=== Step 10: Playing the second AI deck ===")
    play_one_match(controller, "10_match2", DECK_CARD_2_FX, DECK_CARD_2_FY)

    print("\n=== Step 11: Waiting before the third deck ===")
    time.sleep(BETWEEN_MATCHES_WAIT)
    controller.take_screenshot("11_before_match3.png")

    print("\n=== Step 12: Playing the third AI deck ===")
    play_one_match(controller, "12_match3", DECK_CARD_3_FX, DECK_CARD_3_FY)

    print("\nDone. Send me screenshots_tcgp/12_match3_04_after_continue"
          ".png.")
    print("Once I see where this lands (back on the opponent list? "
          "tier list? a 4th deck?), we measure whatever comes next, "
          "same as Raid / Sky Arena.")