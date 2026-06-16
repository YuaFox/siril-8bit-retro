# 8-bit Pixel Art Effect for Siril
# Author: Claude / Anthropic
# License: MIT
# Description: Applies an 8-bit retro pixel art effect to the current image in Siril.
#              Opens a PyQt6 GUI with live preview and sliders to configure the effect.
# Requires: Siril 1.4+

import sys
import numpy as np
import sirilpy as s

s.ensure_installed("PyQt6")
s.ensure_installed("Pillow")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QImage, QPixmap
from PIL import Image

VERSION = "1.2.0"

PREVIEW_MAX = 320  # max px for preview thumbnail dimension

# ── Normalization ─────────────────────────────────────────────────────────────

def _stretch_to_255(arr):
    """
    Stretch a float32 HWC array to the [0, 255] range using percentile clipping.
    Linear astronomical data lives near 0 in a [0, 1] or [0, 65535] range;
    a simple *255 multiplication leaves everything black.  Percentile clipping
    maps the meaningful signal to the full display range, matching what Siril
    shows on screen.
    """
    p_low  = np.percentile(arr, 0.5)
    p_high = np.percentile(arr, 99.5)
    if p_high > p_low:
        arr = np.clip((arr - p_low) / (p_high - p_low) * 255.0, 0, 255)
    else:
        arr = np.zeros_like(arr)
    return arr


# ── Core effect (pure numpy, HWC float32 0–255) ───────────────────────────────

def _process_array(arr, pixel_block, color_levels, saturation, contrast,
                   noise_strength, noise_blue, scanline_step, scanline_dim):
    """Apply the 8-bit effect to a HWC float32 array already in the 0–255 range."""
    h, w, c = arr.shape
    arr = arr.copy()

    # Contrast & saturation
    mean = arr.mean()
    arr = (arr - mean) * contrast + mean
    if c == 3:
        gray = arr.mean(axis=2, keepdims=True)
        arr = gray + (arr - gray) * saturation
    arr = np.clip(arr, 0, 255)

    # Pixelation
    pil_img = Image.fromarray(arr.astype(np.uint8))
    tw, th = max(1, w // pixel_block), max(1, h // pixel_block)
    small = pil_img.resize((tw, th), Image.NEAREST)
    pixelated = small.resize((w, h), Image.NEAREST)
    arr = np.array(pixelated, dtype=np.float32)

    # Color quantization
    step = 256 // color_levels
    arr = (arr // step) * step
    arr = np.clip(arr, 0, 255 - step)

    # Color noise
    if noise_strength > 0:
        noise = np.random.normal(0, noise_strength, arr.shape).astype(np.float32)
        if c == 3:
            noise[:, :, 2] *= noise_blue
        arr = np.clip(arr + noise, 0, 255)

    # CRT scanlines
    if scanline_step > 0:
        step_aligned = pixel_block * scanline_step
        for y in range(0, h, step_aligned):
            arr[y:y+1, :] = arr[y:y+1, :] * scanline_dim

    return arr


# ── Siril integration ─────────────────────────────────────────────────────────

def apply_8bit_effect(siril, pixel_block, color_levels, saturation, contrast,
                      noise_strength, noise_blue, scanline_step, scanline_dim):
    try:
        with siril.image_lock():
            fit = siril.get_image(True)
            data = fit.data.copy().astype(np.float32)

        siril.log("8-bit Pixel Art: aplicando efecto...")

        # CHW → HWC
        if data.ndim == 3:
            arr = np.transpose(data, (1, 2, 0))
        else:
            arr = data[:, :, np.newaxis]

        # Percentile stretch so linear data fills the 0-255 display range
        arr = _stretch_to_255(arr)

        arr = _process_array(arr, pixel_block, color_levels, saturation, contrast,
                             noise_strength, noise_blue, scanline_step, scanline_dim)

        # Back to [0, 1] and CHW
        arr = arr / 255.0
        if data.ndim == 3:
            result = np.transpose(arr, (2, 0, 1))
        else:
            result = arr[:, :, 0]

        result = result.astype(data.dtype)

        with siril.image_lock():
            siril.set_image_pixeldata(result)

        siril.log("8-bit Pixel Art: ¡listo!")

    except Exception as e:
        siril.log(f"Error en el script: {e}")
        raise


# ── GUI ───────────────────────────────────────────────────────────────────────

class SliderRow(QWidget):
    def __init__(self, label, min_val, max_val, default, decimals=0, scale=1):
        super().__init__()
        self.scale = scale
        self.decimals = decimals

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label)
        lbl.setFixedWidth(160)
        layout.addWidget(lbl)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(min_val * scale), int(max_val * scale))
        self.slider.setValue(int(default * scale))
        self.slider.valueChanged.connect(self._update_label)
        layout.addWidget(self.slider)

        self.value_label = QLabel()
        self.value_label.setFixedWidth(45)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.value_label)

        self._update_label()

    def _update_label(self):
        val = self.slider.value() / self.scale
        self.value_label.setText(f"{val:.{self.decimals}f}")

    def value(self):
        return self.slider.value() / self.scale


class PixelArtWindow(QMainWindow):
    def __init__(self, siril):
        super().__init__()
        self.siril = siril
        self._original_data = None  # CHW original dtype — for undo
        self._thumb_hwc = None      # HWC float32 0-255 thumbnail — for preview

        self.setWindowTitle(f"8-bit Pixel Art — v{VERSION}")
        self.setMinimumWidth(720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(16)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Left: preview ──────────────────────────────────────────────────
        self.preview_label = QLabel("Cargando preview...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedSize(PREVIEW_MAX, PREVIEW_MAX)
        self.preview_label.setStyleSheet(
            "background:#111; border:1px solid #444; color:#888;"
        )
        root.addWidget(self.preview_label, 0)

        # ── Right: controls ────────────────────────────────────────────────
        ctrl = QWidget()
        layout = QVBoxLayout(ctrl)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(ctrl, 1)

        title = QLabel("8-bit Pixel Art Effect")
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Pixelado
        grp_pixel = QGroupBox("Pixelado")
        gl = QVBoxLayout(grp_pixel)
        self.s_pixel_block  = SliderRow("Tamaño de bloque", 2, 12, 3)
        self.s_color_levels = SliderRow("Niveles de color", 2, 32, 8)
        gl.addWidget(self.s_pixel_block)
        gl.addWidget(self.s_color_levels)
        layout.addWidget(grp_pixel)

        # Color
        grp_color = QGroupBox("Color")
        gl2 = QVBoxLayout(grp_color)
        self.s_saturation = SliderRow("Saturación", 1.0, 4.0, 2.2, decimals=1, scale=10)
        self.s_contrast   = SliderRow("Contraste",  1.0, 3.0, 1.4, decimals=1, scale=10)
        gl2.addWidget(self.s_saturation)
        gl2.addWidget(self.s_contrast)
        layout.addWidget(grp_color)

        # Ruido
        grp_noise = QGroupBox("Ruido de color")
        gl3 = QVBoxLayout(grp_noise)
        self.s_noise_strength = SliderRow("Intensidad",  0, 40, 0)
        self.s_noise_blue     = SliderRow("Boost azul", 1.0, 4.0, 2.0, decimals=1, scale=10)
        gl3.addWidget(self.s_noise_strength)
        gl3.addWidget(self.s_noise_blue)
        layout.addWidget(grp_noise)

        # CRT
        grp_crt = QGroupBox("Scanlines CRT")
        gl4 = QVBoxLayout(grp_crt)
        self.s_scanline_step = SliderRow("Cada N bloques", 0, 10, 2)
        self.s_scanline_dim  = SliderRow("Oscurecimiento", 0.1, 1.0, 0.55, decimals=2, scale=100)
        gl4.addWidget(self.s_scanline_step)
        gl4.addWidget(self.s_scanline_dim)
        layout.addWidget(grp_crt)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Aplicar efecto")
        self.btn_apply.setFixedHeight(36)
        self.btn_apply.clicked.connect(self.apply)

        self.btn_undo = QPushButton("↩ Revertir")
        self.btn_undo.setFixedHeight(36)
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.revert)

        btn_close = QPushButton("Cerrar")
        btn_close.setFixedHeight(36)
        btn_close.clicked.connect(self.close)

        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_undo)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        # Debounce timer for preview
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._update_preview)

        for row in [self.s_pixel_block, self.s_color_levels,
                    self.s_saturation, self.s_contrast,
                    self.s_noise_strength, self.s_noise_blue,
                    self.s_scanline_step, self.s_scanline_dim]:
            row.slider.valueChanged.connect(self._schedule_preview)

        self._load_image()

    # ── Image loading ──────────────────────────────────────────────────────

    def _load_image(self):
        try:
            with self.siril.image_lock():
                fit = self.siril.get_image(True)
                self._original_data = fit.data.copy()  # original dtype for undo

            data_f32 = self._original_data.astype(np.float32)

            # CHW → HWC
            if data_f32.ndim == 3:
                arr = np.transpose(data_f32, (1, 2, 0))
            else:
                arr = np.stack([data_f32, data_f32, data_f32], axis=2)

            # Percentile stretch: maps the real signal to 0-255 regardless of
            # whether the data is linear [0,1], linear [0,65535], or already stretched
            arr = _stretch_to_255(arr)

            # Downscale to thumbnail
            h, w, _ = arr.shape
            scale = min(PREVIEW_MAX / w, PREVIEW_MAX / h, 1.0)
            tw, th = max(1, int(w * scale)), max(1, int(h * scale))
            pil = Image.fromarray(arr.astype(np.uint8))
            pil = pil.resize((tw, th), Image.NEAREST)
            self._thumb_hwc = np.array(pil, dtype=np.float32)

            self._update_preview()

        except Exception as e:
            self.preview_label.setText(f"Preview no disponible:\n{e}")

    # ── Preview ────────────────────────────────────────────────────────────

    def _schedule_preview(self):
        self._preview_timer.start()

    def _update_preview(self):
        if self._thumb_hwc is None:
            return
        try:
            result = _process_array(self._thumb_hwc, **self._params())
            rgb = result.astype(np.uint8)
            if rgb.shape[2] == 1:
                rgb = np.repeat(rgb, 3, axis=2)
            h, w, _ = rgb.shape
            qimg = QImage(rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
            self.preview_label.setPixmap(
                QPixmap.fromImage(qimg).scaled(
                    PREVIEW_MAX, PREVIEW_MAX,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )
        except Exception as e:
            self.preview_label.setText(f"Error preview:\n{e}")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _params(self):
        return dict(
            pixel_block    = max(1, int(self.s_pixel_block.value())),
            color_levels   = max(2, int(self.s_color_levels.value())),
            saturation     = self.s_saturation.value(),
            contrast       = self.s_contrast.value(),
            noise_strength = self.s_noise_strength.value(),
            noise_blue     = self.s_noise_blue.value(),
            scanline_step  = int(self.s_scanline_step.value()),
            scanline_dim   = self.s_scanline_dim.value(),
        )

    # ── Actions ────────────────────────────────────────────────────────────

    def apply(self):
        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("Procesando...")
        QApplication.processEvents()
        try:
            apply_8bit_effect(self.siril, **self._params())
            self.btn_undo.setEnabled(True)
        finally:
            self.btn_apply.setEnabled(True)
            self.btn_apply.setText("Aplicar efecto")

    def revert(self):
        if self._original_data is None:
            return
        self.btn_undo.setEnabled(False)
        try:
            with self.siril.image_lock():
                self.siril.set_image_pixeldata(self._original_data)
            self.siril.log("8-bit Pixel Art: imagen revertida al estado original.")
        except Exception as e:
            self.siril.log(f"Error al revertir: {e}")
            self.btn_undo.setEnabled(True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    siril = s.SirilInterface()
    try:
        siril.connect()
    except s.SirilConnectionError as e:
        print(f"No se pudo conectar a Siril: {e}")
        sys.exit(1)

    if not siril.is_image_loaded():
        siril.log("8-bit Pixel Art: no hay ninguna imagen cargada.")
        sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)
    window = PixelArtWindow(siril)
    window.show()
    app.exec()

if __name__ == "__main__":
    main()
