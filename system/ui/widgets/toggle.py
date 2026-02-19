import pyray as rl
import math
import random
from collections.abc import Callable
from openpilot.system.ui.lib.application import MousePos
from openpilot.system.ui.widgets import Widget

ON_COLOR = rl.Color(51, 171, 76, 255)
OFF_COLOR = rl.Color(0x39, 0x39, 0x39, 255)
KNOB_COLOR = rl.WHITE
DISABLED_ON_COLOR = rl.Color(0x22, 0x77, 0x22, 255)  # Dark green when disabled + on
DISABLED_OFF_COLOR = rl.Color(0x39, 0x39, 0x39, 255)
DISABLED_KNOB_COLOR = rl.Color(0x88, 0x88, 0x88, 255)
WIDTH, HEIGHT = 160, 80
BG_HEIGHT = 60
ANIMATION_SPEED = 6.0
PRESS_COMMIT_DELAY = 0.14
TOGGLE_FX_DURATION = 0.34
TOGGLE_FX_PARTICLE_COUNT = 14


class Toggle(Widget):
  def __init__(self, initial_state: bool = False, callback: Callable[[bool], None] | None = None):
    super().__init__()
    self._state = initial_state
    self._callback = callback
    self._enabled = True
    self._progress = 1.0 if initial_state else 0.0
    self._target = self._progress
    self._clicked = False
    self._pending_state: bool | None = None
    self._commit_t: float | None = None
    self._pressed_visual_until_t: float = 0.0
    self._toggle_fx_t: float | None = None
    self._toggle_fx_on: bool = initial_state
    self._toggle_fx_particles: list[dict[str, float]] = []

  def set_rect(self, rect: rl.Rectangle):
    self._rect = rl.Rectangle(rect.x, rect.y, WIDTH, HEIGHT)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if not self._enabled:
      return

    # Let pressed visual land before commit (iOS-style).
    if self._commit_t is not None:
      return
    now = rl.get_time()
    self._pressed_visual_until_t = now + PRESS_COMMIT_DELAY
    self._pending_state = not self._state
    self._commit_t = now + PRESS_COMMIT_DELAY

  def get_state(self) -> bool:
    return self._state

  def set_state(self, state: bool):
    self._state = state
    self._target = 1.0 if state else 0.0

  def _trigger_toggle_fx(self, state: bool):
    now = rl.get_time()
    self._toggle_fx_t = now
    self._toggle_fx_on = state
    self._toggle_fx_particles.clear()

    x = self._rect.x + HEIGHT / 2 + (WIDTH - HEIGHT) * (1.0 if state else 0.0)
    y = self._rect.y + HEIGHT / 2
    for i in range(TOGGLE_FX_PARTICLE_COUNT):
      angle = (i / TOGGLE_FX_PARTICLE_COUNT) * 2.0 * math.pi + random.uniform(-0.22, 0.22)
      speed = random.uniform(76.0, 160.0)
      self._toggle_fx_particles.append({
        "x": x,
        "y": y,
        "vx": math.cos(angle) * speed,
        "vy": math.sin(angle) * speed,
        "size": random.uniform(1.8, 3.2),
      })

  def is_enabled(self):
    return self._enabled

  def update(self):
    if abs(self._progress - self._target) > 0.01:
      delta = rl.get_frame_time() * ANIMATION_SPEED
      self._progress += delta if self._progress < self._target else -delta
      self._progress = max(0.0, min(1.0, self._progress))

  def _update_state(self):
    if self._commit_t is not None and rl.get_time() >= self._commit_t:
      self._commit_t = None
      if self._pending_state is not None:
        self._state = self._pending_state
        self._target = 1.0 if self._state else 0.0
        self._trigger_toggle_fx(self._state)
        self._pending_state = None
        self._clicked = True
        if self._callback:
          self._callback(self._state)

  def _render(self, rect: rl.Rectangle):
    self.update()
    pressed_visual = self.is_pressed or rl.get_time() < self._pressed_visual_until_t

    if self._enabled:
      bg_color = self._blend_color(OFF_COLOR, ON_COLOR, self._progress)
      knob_color = KNOB_COLOR
      if pressed_visual:
        bg_color = self._blend_color(bg_color, rl.WHITE, 0.08)
    else:
      bg_color = self._blend_color(DISABLED_OFF_COLOR, DISABLED_ON_COLOR, self._progress)
      knob_color = DISABLED_KNOB_COLOR

    # Draw background
    bg_rect = rl.Rectangle(self._rect.x + 5, self._rect.y + 10, WIDTH - 10, BG_HEIGHT)
    rl.draw_rectangle_rounded(bg_rect, 1.0, 10, bg_color)

    # Draw knob
    knob_x = self._rect.x + HEIGHT / 2 + (WIDTH - HEIGHT) * self._progress
    knob_y = self._rect.y + HEIGHT / 2
    knob_radius = HEIGHT / 2 * (0.94 if pressed_visual else 1.0)
    rl.draw_circle(int(knob_x), int(knob_y), knob_radius, knob_color)

    if self._toggle_fx_t is not None:
      dt = rl.get_time() - self._toggle_fx_t
      if dt > TOGGLE_FX_DURATION:
        self._toggle_fx_t = None
        self._toggle_fx_particles.clear()
      else:
        p = dt / TOGGLE_FX_DURATION
        fade = max(0.0, 1.0 - p)
        ring_r = knob_radius * 0.62 + 34.0 * p
        ring_a = int(255 * (fade ** 1.4) * 0.46)
        ring_color = rl.Color(114, 232, 141, ring_a) if self._toggle_fx_on else rl.Color(148, 182, 255, ring_a)
        rl.draw_circle_lines(int(knob_x), int(knob_y), ring_r, ring_color)
        rl.draw_circle_lines(int(knob_x), int(knob_y), ring_r * 0.73, rl.Color(ring_color.r, ring_color.g, ring_color.b, int(ring_a * 0.65)))
        glow_a = int(255 * (fade ** 1.5) * 0.26)
        rl.draw_circle_gradient(int(knob_x), int(knob_y), knob_radius * (1.15 + 0.45 * p),
                                rl.Color(ring_color.r, ring_color.g, ring_color.b, glow_a),
                                rl.Color(ring_color.r, ring_color.g, ring_color.b, 0))
        for part in self._toggle_fx_particles:
          px = part["x"] + part["vx"] * p
          py = part["y"] + part["vy"] * p - 20.0 * p * (1.0 - p)
          pa = int(255 * (fade ** 1.8) * 0.52)
          pc = rl.Color(ring_color.r, ring_color.g, ring_color.b, pa)
          rl.draw_circle(int(px), int(py), max(1.0, part["size"] * (1.0 - 0.6 * p)), pc)

    # TODO: use click callback
    clicked = self._clicked
    self._clicked = False
    return clicked

  def _blend_color(self, c1, c2, t):
    return rl.Color(int(c1.r + (c2.r - c1.r) * t), int(c1.g + (c2.g - c1.g) * t), int(c1.b + (c2.b - c1.b) * t), 255)
