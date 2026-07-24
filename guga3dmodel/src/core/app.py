"""Main application loop using glfw + moderngl.

Creates a transparent borderless always-on-top window
and renders the 3D pet model.
"""

import math
import sys
import time
import ctypes

import glfw
import moderngl
import numpy as np
from PIL import Image

from config.settings import window as win_cfg, camera as cam_cfg


class GugaApp:
    """Core application with glfw window and OpenGL context."""

    def __init__(self) -> None:
        if not glfw.init():
            raise RuntimeError("glfw init failed")

        glfw.window_hint(glfw.DECORATED, False)
        glfw.window_hint(glfw.FLOATING, True)
        glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, True)
        glfw.window_hint(glfw.VISIBLE, False)
        glfw.window_hint(glfw.DOUBLEBUFFER, True)
        glfw.window_hint(glfw.SAMPLES, 4)

        self.window = glfw.create_window(
            win_cfg.width, win_cfg.height, win_cfg.title, None, None
        )
        if not self.window:
            glfw.terminate()
            raise RuntimeError("window creation failed")

        # Position at bottom-right
        monitor = glfw.get_primary_monitor()
        vmode = glfw.get_video_mode(monitor)
        glfw.set_window_pos(
            self.window,
            vmode.size.width - win_cfg.width - 50,
            vmode.size.height - win_cfg.height - 80
        )

        glfw.make_context_current(self.window)
        glfw.swap_interval(1)

        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.DEPTH_TEST)

        self._pet = None
        self._mouse_down = False
        self._drag_start = (0.0, 0.0)
        self._last_time = time.time()
        self._rotation = 0.0
        self._bob = 0.0
        self._state = "idle"

        glfw.set_mouse_button_callback(self.window, self._on_mouse)
        glfw.set_cursor_pos_callback(self.window, self._on_mouse_move)
        glfw.show_window(self.window)

        # Make always-on-top via Windows API
        self._set_topmost()

    def _set_topmost(self) -> None:
        try:
            hwnd = glfw.get_win32_window(self.window)
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002
            )
        except Exception:
            pass

    def set_pet(self, pet) -> None:
        self._pet = pet

    def run(self) -> None:
        while not glfw.window_should_close(self.window):
            glfw.poll_events()
            now = time.time()
            dt = now - self._last_time
            self._last_time = now

            self._update(dt)
            self._render()

            glfw.swap_buffers(self.window)

        glfw.terminate()

    def _update(self, dt: float) -> None:
        t = time.time()
        if self._state == "sleeping":
            self._bob = math.sin(t * 1.0) * 0.005
            self._rotation += (0.05 - self._rotation) * 1.0 * dt
        elif self._state == "excited":
            self._bob = abs(math.sin(t * 6.0)) * 0.04
            self._rotation = math.sin(t * 10.0) * 0.1
        elif self._state == "thinking":
            self._bob = math.sin(t * 1.8) * 0.008
            self._rotation = 0.12 + math.sin(t * 2.0) * 0.06
        else:
            self._bob = math.sin(t * 2.5) * 0.012
            self._rotation += (0.0 - self._rotation) * 2.0 * dt

    def _render(self) -> None:
        r, g, b, a = win_cfg.bg_color
        self.ctx.clear(r, g, b, a)

        if not self._pet or not self._pet.model.vao:
            return

        # Projection
        proj = self._perspective(
            cam_cfg.fov, win_cfg.width / win_cfg.height, cam_cfg.near, cam_cfg.far
        )

        # View
        view = self._look_at(
            (0, 0, cam_cfg.distance),
            (0, 0.3, 0),
            (0, 1, 0),
        )

        # Model transform
        model = np.identity(4, dtype=np.float32)
        self._translate(model, 0.0, self._bob, 0.0)
        self._rotate_y(model, self._rotation)

        # Apply to shader
        prog = self._pet.model.vao.program
        prog['model'].write(model.T.tobytes())
        prog['view'].write(view.T.tobytes())
        prog['proj'].write(proj.T.tobytes())

        self._pet.model.vao.render(moderngl.TRIANGLES)

    def _on_mouse(self, window, button, action, mods) -> None:
        if button == glfw.MOUSE_BUTTON_LEFT:
            if action == glfw.PRESS:
                self._mouse_down = True
                self._drag_start = glfw.get_cursor_pos(window)
                self._state = "excited"
            elif action == glfw.RELEASE:
                self._mouse_down = False
                self._state = "idle"

    def _on_mouse_move(self, window, x, y) -> None:
        if self._mouse_down:
            dx = x - self._drag_start[0]
            dy = y - self._drag_start[1]
            if abs(dx) > 3 or abs(dy) > 3:
                cur_x, cur_y = glfw.get_window_pos(window)
                glfw.set_window_pos(window, cur_x + int(dx), cur_y + int(dy))

    # ---- Matrix helpers ----

    @staticmethod
    def _perspective(fov, aspect, near, far):
        f = 1.0 / math.tan(math.radians(fov) / 2.0)
        return np.array([
            [f/aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (far+near)/(near-far), (2*far*near)/(near-far)],
            [0, 0, -1, 0],
        ], dtype=np.float32)

    @staticmethod
    def _look_at(eye, center, up):
        f = np.array(center) - np.array(eye); f /= np.linalg.norm(f)
        s = np.cross(f, np.array(up)); s /= np.linalg.norm(s)
        u = np.cross(s, f)
        return np.array([
            [s[0], s[1], s[2], -np.dot(s, eye)],
            [u[0], u[1], u[2], -np.dot(u, eye)],
            [-f[0], -f[1], -f[2], np.dot(f, eye)],
            [0, 0, 0, 1],
        ], dtype=np.float32)

    @staticmethod
    def _translate(m, x, y, z):
        m[0][3] += x; m[1][3] += y; m[2][3] += z

    @staticmethod
    def _rotate_y(m, angle):
        c = math.cos(angle); s = math.sin(angle)
        r = np.array([
            [c, 0, s, 0],
            [0, 1, 0, 0],
            [-s, 0, c, 0],
            [0, 0, 0, 1],
        ], dtype=np.float32)
        m[:] = m @ r