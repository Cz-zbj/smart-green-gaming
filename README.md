# Smart & Green Gaming

**Measuring the battery energy consumption of mobile games on Android, using automated and reproducible gameplay.**

Summer research project at [LASIGE](https://www.lasige.pt/), Faculdade de Ciências da Universidade de Lisboa, supervised by Wellington Oliveira.

![Poster](docs/poster.png)

---

## About

Mobile games are among the most energy-hungry apps on a smartphone, but players rarely know how much in-game settings (graphics quality, frame rate, game speed, animations) actually cost in battery.

This project builds a **reproducible energy benchmarking pipeline** for Android games:

1. The game is played automatically by scripts. There is no human in the loop, so every run follows the same sequence of actions.
2. Each configuration is repeated many times.
3. The battery statistics of every run are collected and compared across configurations.

The goal is to answer questions like *"How much more energy does Ultra graphics use than Medium?"* or *"Does running the game at 3x speed save energy per level?"*

## Games and configurations

| Game | Configurations tested |
|---|---|
| Flow Free | Normal mode; animations disabled |
| Summoners War: Sky Arena | Battle speed x1 / x2 / x3; in-game power-saving ("reduce") mode |
| Raid: Shadow Legends | Graphics quality (Medium / High / Ultra) × frame rate (30 / 60 fps) |
| Pokémon TCG Pocket | Graphics quality (Low / Medium / High) × frame rate (30 / 60 fps) |

## How it works

```
┌──────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ ebserver         │────▶│ Android device       │────▶│ batterystats dump   │
│ (Node.js)        │     │ UI Automator test or │     │ → CSV per run       │
│ runs the queue   │     │ ADB script plays the │     │ → analysis (Python, │
│ of experiments   │     │ game automatically   │     │   Jupyter)          │
└──────────────────┘     └──────────────────────┘     └─────────────────────┘
```

- **Automation**: each game has a Java **UI Automator** test and/or a **Python ADB** script that launches the game, navigates the menus and plays through a fixed scenario.
- **Orchestration**: experiments are queued and executed by [ebserver](https://github.com/wellington-oj/ebserver), an energy-measurement framework by Wellington Oliveira. My integrations for these games are in my fork: [Cz-zbj/ebserver](https://github.com/Cz-zbj/ebserver/tree/smart-green-gaming).
- **Measurement**: before every run, battery statistics are reset (`adb shell dumpsys batterystats --reset`). After the run, the statistics are collected and parsed into CSV.
- **Hardware**: real energy data is collected on a physical device (Samsung Galaxy S20 FE, SM-G780G). Emulators return fixed values from the BatteryManager API, so they were only used for developing the scripts.

## Technical challenges

Some problems I had to solve along the way:

- **Coordinate spaces**: UI Automator's `device.click()` uses display coordinates, while my measured coordinates were in framebuffer space. All taps and swipes go through `input touchscreen` shell commands. Coordinates are stored as fractions of the screen, so they adapt to different resolutions.
- **Waiting for the screen to be ready**: fixed `sleep()` calls were unreliable with animations and network loading. I replaced them with **stability detection**: the script takes screenshots, compares small grayscale thumbnails, and continues only when several consecutive frames are unchanged.
- **Games that change every day**: Sky Arena shows different promotional pop-ups and banners each day, which breaks hard-coded tap sequences. I added handlers for the known pop-ups.
- **Measurement limits**: the device's power profile has no GPU coefficient, so `batterystats` cannot attribute graphics load separately. Per-component attribution is therefore only indicative; the comparisons focus on total energy.

## Results

The full analysis is in the [report](docs/report.pdf).

<!-- TODO: add 2–4 bullet points with your main findings, and a chart image, e.g.
- Raid: Shadow Legends at Ultra used X% more energy than at Medium.
![Energy per configuration](docs/images/results.png)
-->

## Repository structure

```
smart-green-gaming/
├── adb-scripts/   Python ADB automation scripts
├── data/          Collected energy data (CSV)
└── docs/
    ├── report.pdf
    └── poster.pdf
```

The UI Automator tests (`*UiTest.java`) and the ebserver integration live in the [ebserver fork](https://github.com/Cz-zbj/ebserver/tree/smart-green-gaming).

## Running the scripts

Requirements: Python 3, Android SDK platform-tools (`adb`) and an Android device with USB debugging enabled.

```bash
adb devices                      # check that the device is connected
adb shell dumpsys batterystats --reset
python adb-scripts/tcgp_adb_controller.py
```

To run the UI Automator experiments through ebserver, see the [ebserver documentation](https://github.com/wellington-oj/ebserver).

Note: the tap coordinates were calibrated for the screen used in this study. On another device or game version, they may need to be adjusted.

## Future work

- More games
- More configurations

## Disclaimer

This is an academic research project. The scripts only automate normal gameplay to measure energy consumption. They do not modify the games, give any in-game advantage, or collect rewards. All game names and trademarks belong to their respective owners.

## Acknowledgements

- **Wellington Oliveira**, for supervision and for the [ebserver](https://github.com/wellington-oj/ebserver) framework
- **LASIGE**, Faculdade de Ciências da Universidade de Lisboa

## Author

**Cristiano Zhou**, Computer Engineering student at Ciências ULisboa
