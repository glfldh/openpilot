from collections.abc import Callable

import pyray as rl
import math

from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.common.filter_simple import FirstOrderFilter, BounceFilter


class SmallSlider(Widget):
  HORIZONTAL_PADDING = 8
  CONFIRM_DELAY = 0.2
  EXPLOSION_DURATION = 0.7

  def __init__(self, title: str, confirm_callback: Callable | None = None):
    # TODO: unify this with BigConfirmationDialogV2
    super().__init__()
    self._confirm_callback = confirm_callback

    self._font = gui_app.font(FontWeight.DISPLAY)

    self._load_assets()

    self._drag_threshold = -self._rect.width // 2

    # State
    self._opacity_filter = FirstOrderFilter(1.0, 0.1, 1 / gui_app.target_fps)
    self._confirmed_time = 0.0
    self._confirm_callback_called = False  # we keep dialog open by default, only call once
    self._explosion_t: float | None = None
    self._start_x_circle = 0.0
    self._scroll_x_circle = 0.0
    self._scroll_x_circle_filter = BounceFilter(0, 0.06, 1 / gui_app.target_fps)
    self._knob_velocity_filter = FirstOrderFilter(0.0, 0.05, 1 / gui_app.target_fps)
    self._last_knob_x = 0.0
    self._circle_scale_x_filter = BounceFilter(1.0, 0.07, 1 / gui_app.target_fps)
    self._circle_scale_y_filter = BounceFilter(1.0, 0.07, 1 / gui_app.target_fps)
    self._circle_y_jelly_filter = BounceFilter(0.0, 0.08, 1 / gui_app.target_fps)
    self._fx_energy_filter = FirstOrderFilter(0.0, 0.08, 1 / gui_app.target_fps)
    self._handle_center = rl.Vector2(0, 0)

    self._is_dragging_circle = False

    self._label = UnifiedLabel(title, font_size=36, font_weight=FontWeight.MEDIUM, text_color=rl.Color(255, 255, 255, int(255 * 0.65)),
                               alignment=rl.GuiTextAlignment.TEXT_ALIGN_RIGHT,
                               alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE, line_height=0.9)

  def _load_assets(self):
    self.set_rect(rl.Rectangle(0, 0, 316 + self.HORIZONTAL_PADDING * 2, 100))

    self._bg_txt = gui_app.texture("icons_mici/setup/small_slider/slider_bg.png", 316, 100)
    self._circle_bg_txt = gui_app.texture("icons_mici/setup/small_slider/slider_red_circle.png", 100, 100)
    self._circle_arrow_txt = gui_app.texture("icons_mici/setup/small_slider/slider_arrow.png", 37, 32)

  @property
  def confirmed(self) -> bool:
    return self._confirmed_time > 0.0

  def reset(self):
    # reset all slider state
    self._is_dragging_circle = False
    self._confirmed_time = 0.0
    self._confirm_callback_called = False
    self._explosion_t = None

  def set_opacity(self, opacity: float, smooth: bool = False):
    if smooth:
      self._opacity_filter.update(opacity)
    else:
      self._opacity_filter.x = opacity

  @property
  def slider_percentage(self):
    activated_pos = -self._bg_txt.width + self._circle_bg_txt.width
    return min(max(-self._scroll_x_circle_filter.x / abs(activated_pos), 0.0), 1.0)

  @property
  def fx_energy(self) -> float:
    return float(self._fx_energy_filter.x)

  def get_handle_center(self) -> rl.Vector2:
    return self._handle_center

  def _on_confirm(self):
    if self._confirm_callback:
      self._confirm_callback()

  def _handle_mouse_event(self, mouse_event):
    super()._handle_mouse_event(mouse_event)

    if mouse_event.left_pressed:
      # touch rect goes to the padding
      circle_button_rect = rl.Rectangle(
        self._rect.x + (self._rect.width - self._circle_bg_txt.width) + self._scroll_x_circle_filter.x - self.HORIZONTAL_PADDING * 2,
        self._rect.y,
        self._circle_bg_txt.width + self.HORIZONTAL_PADDING * 2,
        self._rect.height,
      )
      if rl.check_collision_point_rec(mouse_event.pos, circle_button_rect):
        self._start_x_circle = mouse_event.pos.x
        self._is_dragging_circle = True

    elif mouse_event.left_released:
      # swiped to left
      if self._scroll_x_circle_filter.x < self._drag_threshold:
        self._confirmed_time = rl.get_time()
        self._explosion_t = rl.get_time()

      self._is_dragging_circle = False

    if self._is_dragging_circle:
      self._scroll_x_circle = mouse_event.pos.x - self._start_x_circle

  def _update_state(self):
    super()._update_state()
    # TODO: this math can probably be cleaned up to remove duplicate stuff
    activated_pos = int(-self._bg_txt.width + self._circle_bg_txt.width)
    self._scroll_x_circle = max(min(self._scroll_x_circle, 0), activated_pos)

    if self._confirmed_time > 0:
      # swiped left to confirm
      self._scroll_x_circle_filter.update(activated_pos)

      # activate once animation completes, small threshold for small floats
      if self._scroll_x_circle_filter.x < (activated_pos + 1):
        if not self._confirm_callback_called and (rl.get_time() - self._confirmed_time) >= self.CONFIRM_DELAY:
          self._on_confirm()
          self._confirm_callback_called = True

    elif not self._is_dragging_circle:
      # reset back to right
      self._scroll_x_circle_filter.update(0)
    else:
      # not activated yet, keep movement 1:1
      self._scroll_x_circle_filter.x = self._scroll_x_circle

    # Knob physics (jelly-like): derive velocity from knob movement.
    dt = max(rl.get_frame_time(), 1e-4)
    knob_v = (self._scroll_x_circle_filter.x - self._last_knob_x) / dt
    self._knob_velocity_filter.update(knob_v)
    self._last_knob_x = self._scroll_x_circle_filter.x

    stretch = min(0.16, abs(self._knob_velocity_filter.x) / 2400.0)
    if self._is_dragging_circle or self._confirmed_time > 0:
      self._circle_scale_x_filter.update(1.0 + stretch)
      self._circle_scale_y_filter.update(1.0 - stretch * 0.70)
    else:
      self._circle_scale_x_filter.update(1.0)
      self._circle_scale_y_filter.update(1.0)

    # Small vertical wobble from horizontal motion makes it feel "alive".
    target_y_jelly = -max(-1.0, min(1.0, self._knob_velocity_filter.x / 2800.0)) * 6.0
    if not self._is_dragging_circle and self._confirmed_time == 0.0:
      target_y_jelly = 0.0
    self._circle_y_jelly_filter.update(target_y_jelly)

    target_fx_energy = 0.0
    if self._is_dragging_circle:
      target_fx_energy = 0.85
    elif self.confirmed:
      target_fx_energy = 0.45
    else:
      target_fx_energy = self.slider_percentage * 0.35
    self._fx_energy_filter.update(target_fx_energy)

  def _render(self, _):
    # TODO: iOS text shimmering animation

    white = rl.Color(255, 255, 255, int(255 * self._opacity_filter.x))

    bg_txt_x = self._rect.x + (self._rect.width - self._bg_txt.width) / 2
    bg_txt_y = self._rect.y + (self._rect.height - self._bg_txt.height) / 2
    rl.draw_texture_ex(self._bg_txt, rl.Vector2(bg_txt_x, bg_txt_y), 0.0, 1.0, white)

    btn_x = bg_txt_x + self._bg_txt.width - self._circle_bg_txt.width + self._scroll_x_circle_filter.x
    btn_y = self._rect.y + (self._rect.height - self._circle_bg_txt.height) / 2
    btn_y += self._circle_y_jelly_filter.x
    self._handle_center = rl.Vector2(btn_x + self._circle_bg_txt.width / 2, btn_y + self._circle_bg_txt.height / 2)

    if self._confirmed_time == 0.0 or self._scroll_x_circle > 0:
      self._label.set_text_color(rl.Color(255, 255, 255, int(255 * 0.65 * (1.0 - self.slider_percentage) * self._opacity_filter.x)))
      label_rect = rl.Rectangle(
        self._rect.x + 20,
        self._rect.y,
        self._rect.width - self._circle_bg_txt.width - 20 * 2.5,
        self._rect.height,
      )
      self._label.render(label_rect)

    # circle and arrow
    scale_x = self._circle_scale_x_filter.x
    scale_y = self._circle_scale_y_filter.x
    src_rec = rl.Rectangle(0, 0, self._circle_bg_txt.width, self._circle_bg_txt.height)
    dest_rec = rl.Rectangle(btn_x + self._circle_bg_txt.width / 2, btn_y + self._circle_bg_txt.height / 2,
                            self._circle_bg_txt.width * scale_x, self._circle_bg_txt.height * scale_y)
    origin = rl.Vector2(dest_rec.width / 2, dest_rec.height / 2)
    rl.draw_texture_pro(self._circle_bg_txt, src_rec, dest_rec, origin, 0.0, white)

    # Alive slider shine around active knob.
    if self._fx_energy_filter.x > 0.01:
      glow_alpha = int(255 * self._opacity_filter.x * (0.08 + 0.30 * self._fx_energy_filter.x))
      glow_r = self._circle_bg_txt.width * (0.45 + 0.18 * self._fx_energy_filter.x * (0.5 + 0.5 * math.sin(rl.get_time() * 10.0)))
      rl.draw_circle_gradient(int(self._handle_center.x), int(self._handle_center.y), glow_r,
                              rl.Color(154, 220, 255, glow_alpha), rl.Color(154, 220, 255, 0))

    arrow_x = btn_x + (self._circle_bg_txt.width - self._circle_arrow_txt.width) / 2
    arrow_y = btn_y + (self._circle_bg_txt.height - self._circle_arrow_txt.height) / 2
    rl.draw_texture_ex(self._circle_arrow_txt, rl.Vector2(arrow_x, arrow_y), 0.0, 1.0, white)

    # Explosion burst when fully activated.
    if self._explosion_t is not None:
      dt = rl.get_time() - self._explosion_t
      if dt < self.EXPLOSION_DURATION:
        p = dt / self.EXPLOSION_DURATION
        cx = btn_x + self._circle_bg_txt.width / 2
        cy = btn_y + self._circle_bg_txt.height / 2
        for i in range(30):
          angle = (i / 30) * (2 * math.pi) + math.sin(i * 1.27) * 0.15
          radius = (34 + (i % 7) * 5) * p
          px = cx + math.cos(angle) * radius
          py = cy + math.sin(angle) * radius
          alpha = int(255 * (1 - p) ** 1.5 * self._opacity_filter.x)
          color = rl.Color(162, 228, 255, alpha) if i % 2 == 0 else rl.Color(196, 150, 255, alpha)
          rl.draw_circle(int(px), int(py), max(1, int(3 - 2 * p)), color)
      else:
        self._explosion_t = None


class LargerSlider(SmallSlider):
  def __init__(self, title: str, confirm_callback: Callable | None = None, green: bool = True):
    self._green = green
    super().__init__(title, confirm_callback=confirm_callback)

  def _load_assets(self):
    self.set_rect(rl.Rectangle(0, 0, 520 + self.HORIZONTAL_PADDING * 2, 115))

    self._bg_txt = gui_app.texture("icons_mici/setup/small_slider/slider_bg_larger.png", 520, 115)
    circle_fn = "slider_green_rounded_rectangle" if self._green else "slider_black_rounded_rectangle"
    self._circle_bg_txt = gui_app.texture(f"icons_mici/setup/small_slider/{circle_fn}.png", 180, 115)
    self._circle_arrow_txt = gui_app.texture("icons_mici/setup/small_slider/slider_arrow.png", 64, 55)


class BigSlider(SmallSlider):
  def __init__(self, title: str, icon: rl.Texture, confirm_callback: Callable | None = None):
    self._icon = icon
    super().__init__(title, confirm_callback=confirm_callback)
    self._label = UnifiedLabel(title, font_size=48, font_weight=FontWeight.DISPLAY, text_color=rl.Color(255, 255, 255, int(255 * 0.65)),
                               alignment=rl.GuiTextAlignment.TEXT_ALIGN_RIGHT, alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE,
                               line_height=0.875)

  def _load_assets(self):
    self.set_rect(rl.Rectangle(0, 0, 520 + self.HORIZONTAL_PADDING * 2, 180))

    self._bg_txt = gui_app.texture("icons_mici/buttons/slider_bg.png", 520, 180)
    self._circle_bg_txt = gui_app.texture("icons_mici/buttons/button_circle.png", 180, 180)
    self._circle_arrow_txt = self._icon


class RedBigSlider(BigSlider):
  def _load_assets(self):
    self.set_rect(rl.Rectangle(0, 0, 520 + self.HORIZONTAL_PADDING * 2, 180))

    self._bg_txt = gui_app.texture("icons_mici/buttons/slider_bg.png", 520, 180)
    self._circle_bg_txt = gui_app.texture("icons_mici/buttons/button_circle_red.png", 180, 180)
    self._circle_arrow_txt = self._icon
