# 8-bit Pixel Art Effect for Siril
# Author: YuaFox
# Assisted by: Claude (Anthropic)
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

VERSION = "1.4.0"

PREVIEW_MAX = 320  # max px for preview thumbnail dimension

# ── Normalización (min/max lineal, como el modo de visualización de Siril) ─────
#
# Las imágenes pueden venir en cualquier rango (16-bit lineal [0,65535], float
# [0,1], etc.). Un simple *255 + cast a uint8 desborda y produce ruido arcoíris.
# Un autostretch MTF agresivo, en cambio, revienta objetos brillantes como la
# Luna a blanco puro. Aquí replicamos el modo "Min/Max + Linear" de Siril:
# escalamos linealmente entre el mínimo y el máximo globales de la imagen. Es
# neutro, preserva el color y coincide con lo que ves en pantalla.

def _to_display_hwc(data, dtype):
    """Datos crudos CHW (cualquier tipo/rango) → HWC float32 en [0,255].

    Escala lineal min/max global (linked) para preservar el balance de color.
    Mono se mantiene como 1 canal (idéntico en preview y en el resultado final).
    """
    arr = data.astype(np.float32)
    if arr.ndim == 3:
        arr = np.transpose(arr, (1, 2, 0))   # CHW → HWC
    else:
        arr = arr[:, :, np.newaxis]

    lo = float(arr.min())
    hi = float(arr.max())
    if hi > lo:
        arr = (arr - lo) / (hi - lo) * 255.0
    else:
        arr = np.zeros_like(arr)
    return arr.astype(np.float32)


# ── Efecto 8-bit (numpy puro, HWC float32 en 0–255) ────────────────────────────
#
# UNA sola función usada tanto por el preview como por el resultado final, sobre
# los mismos datos de origen (el preview solo sobre una copia reducida). Por eso
# ya no pueden divergir.

def _process_array(arr, pixel_block, color_levels, saturation, contrast,
                   noise_strength, noise_blue, scanline_step, scanline_dim,
                   scanline_width=1):
    """Aplica el efecto 8-bit a un HWC float32 ya en el rango 0–255."""
    h, w, c = arr.shape
    arr = arr.copy()

    # 1. Contraste y saturación
    mean = arr.mean()
    arr = (arr - mean) * contrast + mean
    if c == 3:
        gray = arr.mean(axis=2, keepdims=True)
        arr = gray + (arr - gray) * saturation
    arr = np.clip(arr, 0, 255)

    # 2. Pixelado NEAREST
    pil_img = Image.fromarray(arr.astype(np.uint8))
    tw, th = max(1, w // pixel_block), max(1, h // pixel_block)
    small = pil_img.resize((tw, th), Image.NEAREST)
    pixelated = small.resize((w, h), Image.NEAREST)
    arr = np.array(pixelated, dtype=np.float32)
    if arr.ndim == 2:                       # PIL colapsa el canal único en mono
        arr = arr[:, :, np.newaxis]

    # 3. Cuantización de color
    step = 256 // color_levels
    arr = (arr // step) * step
    arr = np.clip(arr, 0, 255 - step)

    # 4. Ruido de color a nivel de bloque, anclado a la paleta
    if noise_strength > 0:
        # Generar ruido a resolución de bloque y escalarlo para que todos los
        # píxeles dentro del mismo bloque reciban el mismo valor de ruido.
        nh = (h + pixel_block - 1) // pixel_block
        nw = (w + pixel_block - 1) // pixel_block
        noise_small = np.random.normal(0, noise_strength, (nh, nw, c)).astype(np.float32)
        if c == 3:
            noise_small[:, :, 2] *= noise_blue
        noise = np.repeat(np.repeat(noise_small, pixel_block, axis=0), pixel_block, axis=1)
        arr = arr + noise[:h, :w]
        # Re-cuantizar para que el resultado siga perteneciendo a la paleta
        arr = (arr // step) * step
        arr = np.clip(arr, 0, 255 - step)

    # 5. Scanlines CRT centradas en los límites entre bloques
    if scanline_step > 0:
        half_t = scanline_width // 2
        rest_t = scanline_width - half_t
        boundary_step = pixel_block * scanline_step
        for b in range(pixel_block, h + pixel_block, boundary_step):
            y_start = max(0, b - half_t)
            y_end = min(h, b + rest_t)
            if y_start < y_end:
                arr[y_start:y_end, :] *= scanline_dim

    return arr


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
        self._original_data = None  # CHW, tipo original — para el undo
        self._orig_dtype = None
        self._display_hwc = None    # HWC float32 0-255 full-res — apply
        self._thumb_hwc = None      # copia reducida de _display_hwc — preview
        self._thumb_scale = 1.0     # factor de reducción del thumbnail

        self.setWindowTitle(f"8-bit Pixel Art — v{VERSION}")
        self.setMinimumWidth(720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(16)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Izquierda: preview ────────────────────────────────────────────
        self.preview_label = QLabel("Cargando preview...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedSize(PREVIEW_MAX, PREVIEW_MAX)
        self.preview_label.setStyleSheet(
            "background:#111; border:1px solid #444; color:#888;"
        )
        root.addWidget(self.preview_label, 0)

        # ── Derecha: controles ───────────────────────────────────────────
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
        self.s_scanline_step  = SliderRow("Cada N bloques", 0, 10, 2)
        self.s_scanline_dim   = SliderRow("Oscurecimiento", 0.1, 1.0, 0.55, decimals=2, scale=100)
        self.s_scanline_width = SliderRow("Grosor (píxeles)", 1, 16, 1)
        gl4.addWidget(self.s_scanline_step)
        gl4.addWidget(self.s_scanline_dim)
        gl4.addWidget(self.s_scanline_width)
        layout.addWidget(grp_crt)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # Botones
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

        # Timer de debounce para el preview
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._update_preview)

        for row in [self.s_pixel_block, self.s_color_levels,
                    self.s_saturation, self.s_contrast,
                    self.s_noise_strength, self.s_noise_blue,
                    self.s_scanline_step, self.s_scanline_dim,
                    self.s_scanline_width]:
            row.slider.valueChanged.connect(self._schedule_preview)

        self._load_image()

    # ── Carga de imagen ──────────────────────────────────────────────────

    def _load_image(self):
        """Captura la imagen original una sola vez y prepara el origen común."""
        try:
            with self.siril.image_lock():
                fit = self.siril.get_image(True)
                self._original_data = fit.data.copy()   # exacto, para revertir
                self._orig_dtype = fit.data.dtype

            # Origen común (full-res, normalizado a 0-255) para preview y apply
            self._display_hwc = _to_display_hwc(self._original_data, self._orig_dtype)

            # Thumbnail = copia reducida del MISMO origen
            h, w, _ = self._display_hwc.shape
            self._thumb_scale = min(PREVIEW_MAX / w, PREVIEW_MAX / h, 1.0)
            tw, th = max(1, int(w * self._thumb_scale)), max(1, int(h * self._thumb_scale))
            pil = Image.fromarray(self._display_hwc.astype(np.uint8))
            pil = pil.resize((tw, th), Image.NEAREST)
            thumb = np.array(pil, dtype=np.float32)
            if thumb.ndim == 2:
                thumb = thumb[:, :, np.newaxis]
            self._thumb_hwc = thumb

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
            params = self._params()
            # El tamaño de bloque va en píxeles: lo escalamos al thumbnail para que
            # el pixelado se vea proporcional al resultado a resolución completa.
            params["pixel_block"] = max(1, round(params["pixel_block"] * self._thumb_scale))
            result = _process_array(self._thumb_hwc, **params)

            rgb = result.astype(np.uint8)
            if rgb.shape[2] == 1:
                rgb = np.repeat(rgb, 3, axis=2)
            rgb = np.ascontiguousarray(rgb)
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
            scanline_width = max(1, int(self.s_scanline_width.value())),
        )

    # ── Acciones ─────────────────────────────────────────────────────────

    def apply(self):
        """Aplica el efecto SIEMPRE desde el origen capturado (idempotente)."""
        if self._display_hwc is None:
            return
        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("Procesando...")
        QApplication.processEvents()
        try:
            self.siril.log("8-bit Pixel Art: aplicando efecto...")
            result = _process_array(self._display_hwc, **self._params())  # HWC [0,255]

            out01 = np.clip(result / 255.0, 0.0, 1.0)
            # HWC → al formato/rango originales
            if self._original_data.ndim == 3:
                out = np.transpose(out01, (2, 0, 1))            # → CHW
            else:
                out = out01[:, :, 0]                            # → HW (mono)

            if np.issubdtype(self._orig_dtype, np.integer):
                out = (out * np.iinfo(self._orig_dtype).max)
            out = out.astype(self._orig_dtype)

            with self.siril.image_lock():
                self.siril.set_image_pixeldata(out)

            self.siril.log("8-bit Pixel Art: ¡listo!")
            self.btn_undo.setEnabled(True)
        except Exception as e:
            self.siril.log(f"Error en el script: {e}")
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


# ── Main ───────────────────────────────────────────────────────────────────────

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
