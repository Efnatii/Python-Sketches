import os
import sys

if os.name != "nt":  # 'nt' — это Windows
    sys.exit("Этот скрипт работает только под Windows.")

import ctypes
from ctypes import wintypes

import PIL
from PIL import Image, ImageDraw

import pygame

from enum import Enum


class Resolution(Enum):
    SQUARE = "1:1"
    WIDESCREEN_16_9 = "16:9"
    CINEMA_21_9 = "21:9"
    PORTRAIT_3_4 = "3:4"
    PORTRAIT_9_16 = "9:16"
    CLASSIC_4_3 = "4:3"
    STANDARD_5_4 = "5:4"
    ULTRAWIDE_32_9 = "32:9"

    def size(self):
        match self:
            case Resolution.SQUARE:
                return (800, 800)
            case Resolution.WIDESCREEN_16_9:
                return (1280, 720)
            case Resolution.CINEMA_21_9:
                return (1680, 720)
            case Resolution.PORTRAIT_3_4:
                return (600, 800)
            case Resolution.PORTRAIT_9_16:
                return (405, 720)
            case Resolution.CLASSIC_4_3:
                return (1024, 768)
            case Resolution.STANDARD_5_4:
                return (1280, 1024)
            case Resolution.ULTRAWIDE_32_9:
                return (2560, 720)
            case _:
                return (800, 600)


from typing import Callable, Optional


class PILSurface:
    def __init__(self, pil_image: Image.Image, position=(0, 0)):
        self.original = pil_image.convert("RGBA")
        self._position = list(position)
        self._scale = 1.0
        self._current = self.original.copy()
        self._cached_surface = None
        self._draw_fn: Optional[Callable] = None  # сохранённая функция рисования

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, factor: float):
        self._scale = factor
        self._resize_current()
        self._cached_surface = None

    @property
    def position(self) -> tuple[int, int]:
        return tuple(self._position)

    @position.setter
    def position(self, value: tuple[int, int]):
        self._position[0], self._position[1] = value

    @property
    def x(self) -> int:
        return self._position[0]

    @x.setter
    def x(self, value: int):
        self._position[0] = value

    @property
    def y(self) -> int:
        return self._position[1]

    @y.setter
    def y(self, value: int):
        self._position[1] = value

    def _resize_current(self):
        self._current = self.original.resize((
            int(self.original.width * self._scale),
            int(self.original.height * self._scale)
        ), Image.LANCZOS)

    def draw(self, func: Optional[Callable] = None, *args, **kwargs):
        if func is not None and callable(func):
            # Использован как декоратор — сохраняем
            self._draw_fn = func
            return func
        elif self._draw_fn is not None:
            # Вызван напрямую — применяем сохранённую функцию
            draw = ImageDraw.Draw(self.original)
            self._draw_fn(draw, *args, **kwargs)
            self._resize_current()
            self._cached_surface = None
        else:
            raise ValueError("Функция рисования не зарегистрирована.")

    def to_surface(self) -> pygame.Surface:
        if self._cached_surface is None:
            self._cached_surface = pygame.image.fromstring(
                self._current.tobytes(),
                self._current.size,
                self._current.mode
            )
        return self._cached_surface

    def __iter__(self):
        yield self.to_surface()
        yield tuple(self._position)


class App:
    def __init__(self, resolution=Resolution.WIDESCREEN_16_9, title="My Pygame Window", scale=1.0,
                 autoscale_to_screen=True, autocenter_window=True):
        pygame.init()

        self.resolution = resolution
        self.initial_width, self.initial_height = self.resolution.size()
        self.aspect = self.initial_width / self.initial_height
        self.scale = scale
        self.width = int(self.initial_width * self.scale)
        self.height = int(self.initial_height * self.scale)

        self.autoscale_to_screen = autoscale_to_screen
        self.autocenter_window = autocenter_window

        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self.hwnd = pygame.display.get_wm_info().get('window')
        pygame.display.set_caption(title)
        self.clock = pygame.time.Clock()

        self.running = True

        self._shrink_to_fit_if()
        self._move_to_center_if()

        self._frame_styled()

    def _frame_styled(self):
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMNCRP_RECTANGLE = 1
        corner_preference = ctypes.c_int(DWMNCRP_RECTANGLE)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(self.hwnd),
            wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference)
        )

    def _move_to_center_if(self):
        if self.autocenter_window:
            ctypes.windll.user32.SetWindowPos(self.hwnd, 0,
                                                  ((ctypes.windll.user32.GetSystemMetrics(0) - self.width) // 2),
                                                  ((ctypes.windll.user32.GetSystemMetrics(1) - self.height) // 2),
                                                  0, 0, 0x0001 | 0x0004 | 0x0400)
            pygame.event.clear([pygame.WINDOWMOVED])

    def _shrink_to_fit_if(self):
            if self.autoscale_to_screen:
                self.scale = min(ctypes.windll.user32.GetSystemMetrics(0) / self.width,
                                 ctypes.windll.user32.GetSystemMetrics(1) / self.height, self.scale)
                self.width = int(self.initial_width * self.scale)
                self.height = int(self.initial_height * self.scale)
                ctypes.windll.user32.SetWindowPos(self.hwnd, 0, 0, 0, self.width, self.height, 0x0002 | 0x0004 | 0x0400)
                pygame.event.clear([pygame.WINDOWRESIZED, pygame.VIDEORESIZE])

    def _resize_to_fit_the_resolution(self, new_width, new_height):
        if abs(new_width - self.width) >= abs(new_height - self.height):
            self.width = new_width
            self.height = int(new_width / self.aspect)
        else:
            self.height = new_height
            self.width = int(new_height * self.aspect)

        self.scale = self.width / self.initial_width
        ctypes.windll.user32.SetWindowPos(self.hwnd, 0, 0, 0, self.width, self.height, 0x0002 | 0x0004 | 0x0400)
        pygame.event.clear([pygame.VIDEORESIZE])


    def handle_events(self):
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.VIDEORESIZE:
                self._resize_to_fit_the_resolution(event.w, event.h)

            elif event.type == pygame.WINDOWRESIZED:
                self._shrink_to_fit_if()
                self._move_to_center_if()

            elif event.type == pygame.WINDOWMOVED:
                self._move_to_center_if()

    def update(self):
        pass

    def draw(self):
        self.screen.fill((255, 255, 255))

        #pygame.surfarray.blit_array(screen, np_image)

    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    app = App(
        resolution=Resolution.WIDESCREEN_16_9,
        scale=1,
        autoscale_to_screen=True,
        autocenter_window=True
    )
    app.run()
