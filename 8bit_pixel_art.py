# 8-bit Pixel Art Effect for Siril
# Author: Claude / Anthropic
# License: MIT
# Description: Applies an 8-bit retro pixel art effect to the current image in Siril.
#              Opens a PyQt6 GUI with sliders to configure the effect before applying.
# Requires: Siril 1.4+

import sys
import numpy as np
import sirilpy as s

s.ensure_installed("PyQt6")
s.ensure_installed("Pillow")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QGroupBox, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PIL import Image

VERSION = "1.0.0"

# ── Lógica del efecto ────────────────────────────────────────────────

def apply_8bit_effect(siril, pixel_block, color_levels, saturation, contrast,
                      noise_strength, noise_blue, scanline_step, scanline_dim):
    try:
        with siril.image_lock():
            fit = siril.get_image(True)
            data = fit.data.copy().astype(np.float32)

        siril.log("8-bit Pixel Art: aplicando efecto...")

        # Siril almacena datos como CHW → convertir a HWC
        if data.ndim == 3:
            arr = np.transpose(data, (1, 2, 0))
        else:
            arr = data[:, :, np.newaxis]

        # Normalizar a 0–255 si está en rango 0–1
        if arr.max() <= 1.0:
            arr = arr * 255.0

        h, w, c = arr.shape

        # 1. Contraste y saturación
        mean = arr.mean()
        arr = (arr - mean) * contrast + mean
        if c == 3:
            gray = arr.mean(axis=2, keepdims=True)
            arr = gray + (arr - gray) * saturation
        arr = np.clip(arr, 0, 255)

        # 2. Pixelado NEAREST
        pil_img = Image.fromarray(arr.astype(np.uint8))
        small = pil_img.resize((w // pixel_block, h // pixel_block), Image.NEAREST)
        pixelated = small.resize((w, h), Image.NEAREST)
        arr = np.array(pixelated, dtype=np.float32)

        # 3. Cuantización de color
        step = 256 // color_levels
        arr = (arr // step) * step
        arr = np.clip(arr, 0, 255 - step)

        # 4. Ruido de color
        if noise_strength > 0:
            noise = np.random.normal(0, noise_strength, arr.shape).astype(np.float32)
            if c == 3:
                noise[:, :, 2] *= noise_blue
            arr = np.clip(arr + noise, 0, 255)

        # 5. Scanlines CRT alineadas al tamaño de bloque
        if scanline_step > 0:
            step_aligned = pixel_block * scanline_step
            for y in range(0, h, step_aligned):
                arr[y:y+1, :] = arr[y:y+1, :] * scanline_dim

        # Volver a rango 0–1 y formato CHW
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


# ── GUI PyQt6 ────────────────────────────────────────────────

class SliderRow(QWidget):
    """Fila de slider con etiqueta y valor numérico."""
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
        self.setWindowTitle(f"8-bit Pixel Art — v{VERSION}")
        self.setMinimumWidth(480)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Título
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

        # Grupo: Pixelado
        grp_pixel = QGroupBox("Pixelado")
        grp_layout = QVBoxLayout(grp_pixel)
        self.s_pixel_block  = SliderRow("Tamaño de bloque", 2, 12, 3, decimals=0, scale=1)
        self.s_color_levels = SliderRow("Niveles de color", 2, 32, 8, decimals=0, scale=1)
        grp_layout.addWidget(self.s_pixel_block)
        grp_layout.addWidget(self.s_color_levels)
        layout.addWidget(grp_pixel)

        # Grupo: Color
        grp_color = QGroupBox("Color")
        grp_layout2 = QVBoxLayout(grp_color)
        self.s_saturation = SliderRow("Saturación", 1.0, 4.0, 2.2, decimals=1, scale=10)
        self.s_contrast   = SliderRow("Contraste",  1.0, 3.0, 1.4, decimals=1, scale=10)
        grp_layout2.addWidget(self.s_saturation)
        grp_layout2.addWidget(self.s_contrast)
        layout.addWidget(grp_color)

        # Grupo: Ruido
        grp_noise = QGroupBox("Ruido de color")
        grp_layout3 = QVBoxLayout(grp_noise)
        self.s_noise_strength = SliderRow("Intensidad",      0, 40,  0, decimals=0, scale=1)
        self.s_noise_blue     = SliderRow("Boost azul",  1.0, 4.0, 2.0, decimals=1, scale=10)
        grp_layout3.addWidget(self.s_noise_strength)
        grp_layout3.addWidget(self.s_noise_blue)
        layout.addWidget(grp_noise)

        # Grupo: Scanlines CRT
        grp_crt = QGroupBox("Scanlines CRT")
        grp_layout4 = QVBoxLayout(grp_crt)
        self.s_scanline_step = SliderRow("Cada N bloques", 0, 10, 2, decimals=0, scale=1)
        self.s_scanline_dim  = SliderRow("Oscurecimiento", 0.1, 1.0, 0.55, decimals=2, scale=100)
        grp_layout4.addWidget(self.s_scanline_step)
        grp_layout4.addWidget(self.s_scanline_dim)
        layout.addWidget(grp_crt)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # Botones
        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("Aplicar efecto")
        self.btn_apply.setFixedHeight(36)
        self.btn_apply.clicked.connect(self.apply)
        btn_close = QPushButton("Cerrar")
        btn_close.setFixedHeight(36)
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def apply(self):
        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("Procesando...")
        QApplication.processEvents()
        try:
            apply_8bit_effect(
                self.siril,
                pixel_block    = int(self.s_pixel_block.value()),
                color_levels   = int(self.s_color_levels.value()),
                saturation     = self.s_saturation.value(),
                contrast       = self.s_contrast.value(),
                noise_strength = self.s_noise_strength.value(),
                noise_blue     = self.s_noise_blue.value(),
                scanline_step  = int(self.s_scanline_step.value()),
                scanline_dim   = self.s_scanline_dim.value(),
            )
        finally:
            self.btn_apply.setEnabled(True)
            self.btn_apply.setText("Aplicar efecto")


# ── Entrada principal ──────────────────────────────────────────────────

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
