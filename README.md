# 8-bit Pixel Art Effect for Siril

A Python script for [Siril](https://siril.org) that applies a retro 8-bit pixel art effect to the currently loaded image. A PyQt6 GUI with **live preview** lets you fine-tune every parameter before the effect is applied. A **Revert** button restores the original if you don't like the result.

---

## Features

| Control | What it does |
|---|---|
| **Block size** | Size of each "pixel" block (2 – 12 px) |
| **Color levels** | Number of quantisation levels per channel (2 – 32) |
| **Saturation** | Colour boost factor (1× – 4×) |
| **Contrast** | Contrast multiplier (1× – 3×) |
| **Noise intensity** | Amount of random colour noise (0 – 40) |
| **Blue boost** | Extra noise amplification on the blue channel (1× – 4×) |
| **Scanlines every N blocks** | CRT horizontal-line frequency (0 = off) |
| **Scanline dimming** | Brightness of the scanline rows (0.1 – 1.0) |

### Live preview

A 320 × 320 thumbnail updates in real time (150 ms debounce) as you move any slider, so you see the result before touching the full-resolution image.

### Undo (one level)

The original pixel data is captured when the window opens. Click **↩ Revertir** at any time to restore the image to its exact pre-effect state.

---

## Requirements

| Dependency | Minimum version |
|---|---|
| Siril | **1.4** |
| Python (bundled with Siril) | 3.10+ |
| sirilpy | bundled with Siril 1.4+ |
| PyQt6 | auto-installed by the script |
| Pillow | auto-installed by the script |
| NumPy | auto-installed by the script |

> `PyQt6`, `Pillow`, and `NumPy` are installed automatically the first time you run the script via `sirilpy.ensure_installed()`.

---

## Installation

### Windows — automatic (recommended)

1. Download both `8bit_pixel_art.py` and `install.ps1` into the **same folder**.
2. Right-click `install.ps1` and choose **"Run with PowerShell"**.
   - The script searches the following default locations for Siril’s scripts directory:
     - `%APPDATA%\siril\scripts`
     - `%LOCALAPPDATA%\siril\scripts`
     - `C:\Program Files\Siril\scripts`
     - `C:\Program Files (x86)\Siril\scripts`
   - If a directory is found, `8bit_pixel_art.py` is copied there automatically.
   - If **no directory is found**, the installer prints an error and manual-install instructions (see below).
3. Restart Siril.

> **Note:** Windows may ask you to confirm running an unsigned script. If the execution policy blocks it, open PowerShell as Administrator and run:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### Windows / Linux / macOS — manual

1. Open Siril and go to **Preferences → Folders**.
2. Note the path listed under **Scripts directory**.
3. Copy `8bit_pixel_art.py` into that folder.
4. Restart Siril.

### Linux / macOS — common default paths

| OS | Default path |
|---|---|
| Linux | `~/.siril/scripts/` |
| macOS | `~/Library/Application Support/siril/scripts/` |

---

## Usage

1. Open an image in Siril.
2. Go to **Tools → Scripts → 8bit_pixel_art**.
3. A window opens with a **live preview** on the left and sliders on the right.
4. Adjust the parameters — the preview updates automatically.
5. Click **"Aplicar efecto"** to apply the effect to the full-resolution image in Siril.
6. Click **"↩ Revertir"** to undo and restore the original image.

---

## Parameter guide

```
Block size 3 + Color levels 8  →  classic NES / Game Boy look
Block size 2 + Color levels 16 →  SNES / 16-bit feel
Scanlines every 2 blocks, dimming 0.5  →  CRT monitor simulation
Noise 10–20 + Blue boost 2.0  →  VHS colour noise
```

---

## License

MIT — see [LICENSE](LICENSE) or the header of `8bit_pixel_art.py`.
