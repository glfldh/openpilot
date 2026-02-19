from __future__ import annotations

import abc
import math
import pyray as rl
from enum import IntEnum
from collections.abc import Callable
from openpilot.common.filter_simple import BounceFilter, FirstOrderFilter
from openpilot.system.ui.lib.application import gui_app, MousePos, MAX_TOUCH_SLOTS, MouseEvent

try:
  from openpilot.selfdrive.ui.ui_state import device
except ImportError:
  class Device:
    awake = True
  device = Device()


class DialogResult(IntEnum):
  CANCEL = 0
  CONFIRM = 1
  NO_ACTION = -1


class Widget(abc.ABC):
  def __init__(self):
    self._rect: rl.Rectangle = rl.Rectangle(0, 0, 0, 0)
    self._parent_rect: rl.Rectangle | None = None
    self.__is_pressed = [False] * MAX_TOUCH_SLOTS
    # if current mouse/touch down started within the widget's rectangle
    self.__tracking_is_pressed = [False] * MAX_TOUCH_SLOTS
    self._enabled: bool | Callable[[], bool] = True
    self._is_visible: bool | Callable[[], bool] = True
    self._touch_valid_callback: Callable[[], bool] | None = None
    self._click_callback: Callable[[], None] | None = None
    self._multi_touch = False
    self.__was_awake = True

  @property
  def rect(self) -> rl.Rectangle:
    return self._rect

  def set_rect(self, rect: rl.Rectangle) -> None:
    changed = (self._rect.x != rect.x or self._rect.y != rect.y or
               self._rect.width != rect.width or self._rect.height != rect.height)
    self._rect = rect
    if changed:
      self._update_layout_rects()

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    """Can be used like size hint in QT"""
    self._parent_rect = parent_rect

  @property
  def is_pressed(self) -> bool:
    return any(self.__is_pressed)

  @property
  def enabled(self) -> bool:
    return self._enabled() if callable(self._enabled) else self._enabled

  def set_enabled(self, enabled: bool | Callable[[], bool]) -> None:
    self._enabled = enabled

  @property
  def is_visible(self) -> bool:
    return self._is_visible() if callable(self._is_visible) else self._is_visible

  def set_visible(self, visible: bool | Callable[[], bool]) -> None:
    self._is_visible = visible

  def set_click_callback(self, click_callback: Callable[[], None] | None) -> None:
    """Set a callback to be called when the widget is clicked."""
    self._click_callback = click_callback

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    """Set a callback to determine if the widget can be clicked."""
    self._touch_valid_callback = touch_callback

  def _touch_valid(self) -> bool:
    """Check if the widget can be touched."""
    return self._touch_valid_callback() if self._touch_valid_callback else True

  def set_position(self, x: float, y: float) -> None:
    changed = (self._rect.x != x or self._rect.y != y)
    self._rect = rl.Rectangle(x, y, self._rect.width, self._rect.height)
    if changed:
      self._update_layout_rects()

  @property
  def _hit_rect(self) -> rl.Rectangle:
    # restrict touches to within parent rect if set, useful inside Scroller
    if self._parent_rect is None:
      return self._rect
    return rl.get_collision_rec(self._rect, self._parent_rect)

  def render(self, rect: rl.Rectangle | None = None) -> bool | int | None:
    if rect is not None:
      self.set_rect(rect)

    self._update_state()

    if not self.is_visible:
      return None

    self._layout()
    ret = self._render(self._rect)

    # Keep track of whether mouse down started within the widget's rectangle
    if self.enabled and self.__was_awake:
      self._process_mouse_events()

    self.__was_awake = device.awake

    return ret

  def _process_mouse_events(self) -> None:
    hit_rect = self._hit_rect
    touch_valid = self._touch_valid()

    for mouse_event in gui_app.mouse_events:
      if not self._multi_touch and mouse_event.slot != 0:
        continue

      mouse_in_rect = rl.check_collision_point_rec(mouse_event.pos, hit_rect)
      # Ignores touches/presses that start outside our rect
      # Allows touch to leave the rect and come back in focus if mouse did not release
      if mouse_event.left_pressed and touch_valid:
        if mouse_in_rect:
          self._handle_mouse_press(mouse_event.pos)
          self.__is_pressed[mouse_event.slot] = True
          self.__tracking_is_pressed[mouse_event.slot] = True
          self._handle_mouse_event(mouse_event)

      # Callback such as scroll panel signifies user is scrolling
      elif not touch_valid:
        self.__is_pressed[mouse_event.slot] = False
        self.__tracking_is_pressed[mouse_event.slot] = False

      elif mouse_event.left_released:
        self._handle_mouse_event(mouse_event)
        if self.__is_pressed[mouse_event.slot] and mouse_in_rect:
          self._handle_mouse_release(mouse_event.pos)
        self.__is_pressed[mouse_event.slot] = False
        self.__tracking_is_pressed[mouse_event.slot] = False

      # Mouse/touch is still within our rect
      elif mouse_in_rect:
        if self.__tracking_is_pressed[mouse_event.slot]:
          self.__is_pressed[mouse_event.slot] = True
          self._handle_mouse_event(mouse_event)

      # Mouse/touch left our rect but may come back into focus later
      elif not mouse_in_rect:
        self.__is_pressed[mouse_event.slot] = False
        self._handle_mouse_event(mouse_event)

  def _layout(self) -> None:
    """Optionally lay out child widgets separately. This is called before rendering."""

  def _update_state(self):
    """Optionally update the widget's non-layout state. This is called before rendering."""

  @abc.abstractmethod
  def _render(self, rect: rl.Rectangle) -> bool | int | None:
    """Render the widget within the given rectangle."""

  def _update_layout_rects(self) -> None:
    """Optionally update any layout rects on Widget rect change."""

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    """Optionally handle mouse press events."""

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    """Optionally handle mouse release events."""
    if self._click_callback:
      self._click_callback()

  def _handle_mouse_event(self, mouse_event: MouseEvent) -> None:
    """Optionally handle mouse events. This is called before rendering."""
    # Default implementation does nothing, can be overridden by subclasses

  def show_event(self):
    """Optionally handle show event. Parent must manually call this"""

  def hide_event(self):
    """Optionally handle hide event. Parent must manually call this"""


SWIPE_AWAY_THRESHOLD = 80  # px to dismiss after releasing
START_DISMISSING_THRESHOLD = 40  # px to start dismissing while dragging
BLOCK_SWIPE_AWAY_THRESHOLD = 60  # px horizontal movement to block swipe away

NAV_BAR_MARGIN = 6
NAV_BAR_WIDTH = 205
NAV_BAR_HEIGHT = 8

DISMISS_PUSH_OFFSET = 50 + NAV_BAR_MARGIN + NAV_BAR_HEIGHT  # px extra to push down when dismissing
DISMISS_TIME_SECONDS = 2.0
NAV_EPIC_PARTICLE_COUNT = 9
NAV_EPIC_AURA_MAX_ALPHA = 92
NAV_INTRO_BOUNCE_TIME = 0.55
NAV_INTRO_PARTICLE_BOOST = 10
NAV_SHOW_EXPLOSION_DURATION = 0.62
NAV_SHOW_EXPLOSION_PARTICLES = 26


class NavBar(Widget):
  def __init__(self):
    super().__init__()
    self.set_rect(rl.Rectangle(0, 0, NAV_BAR_WIDTH, NAV_BAR_HEIGHT))
    self._alpha = 1.0
    self._alpha_filter = FirstOrderFilter(1.0, 0.1, 1 / gui_app.target_fps)
    self._energy = 0.0
    self._energy_filter = FirstOrderFilter(0.0, 0.09, 1 / gui_app.target_fps)
    self._drag_progress = 0.0
    self._drag_progress_filter = FirstOrderFilter(0.0, 0.07, 1 / gui_app.target_fps)
    self._fade_time = 0.0

  def set_alpha(self, alpha: float) -> None:
    self._alpha = alpha
    self._fade_time = rl.get_time()

  def set_energy(self, energy: float) -> None:
    self._energy = min(1.0, max(0.0, energy))

  def set_drag_progress(self, progress: float) -> None:
    self._drag_progress = min(1.0, max(0.0, progress))

  def show_event(self):
    super().show_event()
    self._alpha = 1.0
    self._alpha_filter.x = 1.0
    self._energy = 0.0
    self._energy_filter.x = 0.0
    self._drag_progress = 0.0
    self._drag_progress_filter.x = 0.0
    self._fade_time = rl.get_time()

  def _render(self, _):
    if rl.get_time() - self._fade_time > DISMISS_TIME_SECONDS:
      self._alpha = 0.0
    alpha = self._alpha_filter.update(self._alpha)
    energy = self._energy_filter.update(self._energy)
    drag = self._drag_progress_filter.update(self._drag_progress)
    t = rl.get_time()

    # Alive shape response: stretches and glows more during energetic swipe motion.
    width_scale = 1.0 + 0.16 * energy + 0.20 * drag
    height_scale = 1.0 + 0.20 * drag
    bar_w = self._rect.width * width_scale
    bar_h = max(4.0, self._rect.height * height_scale)
    bar_x = self._rect.x + (self._rect.width - bar_w) / 2
    bar_y = self._rect.y + (self._rect.height - bar_h) / 2
    bar_rect = rl.Rectangle(bar_x, bar_y, bar_w, bar_h)

    glow_rect = rl.Rectangle(bar_rect.x - 10, bar_rect.y - 6, bar_rect.width + 20, bar_rect.height + 12)
    glow_roundness = 1.0
    glow_alpha = int(255 * alpha * (0.04 + 0.22 * energy + 0.24 * drag))
    rl.draw_rectangle_rounded(glow_rect, glow_roundness, 10, rl.Color(112, 194, 255, glow_alpha))

    base_color = rl.Color(245, 248, 255, int(255 * alpha * (0.80 + 0.20 * energy)))
    rl.draw_rectangle_rounded(bar_rect, 1.0, 10, base_color)

    # Gloss strip + sweep for liquid feel.
    gloss_h = max(2, int(bar_rect.height * 0.55))
    rl.draw_rectangle_gradient_v(int(bar_rect.x), int(bar_rect.y), int(bar_rect.width), gloss_h,
                                 rl.Color(255, 255, 255, int(255 * alpha * (0.24 + 0.16 * energy))),
                                 rl.Color(255, 255, 255, 0))

    sweep = 0.5 + 0.5 * math.sin(t * (3.8 + 1.4 * energy))
    streak_x = int(bar_rect.x + bar_rect.width * (0.12 + 0.76 * sweep))
    streak_h = max(2, int(bar_rect.height - 2))
    streak_y = int(bar_rect.y + (bar_rect.height - streak_h) / 2)
    streak_w = max(5, int(8 + 12 * energy))
    streak_alpha = int(255 * alpha * (0.12 + 0.26 * energy))
    streak_color = rl.Color(255, 255, 255, streak_alpha)
    rl.draw_rectangle_gradient_h(streak_x - streak_w, streak_y, streak_w, streak_h, rl.Color(255, 255, 255, 0), streak_color)
    rl.draw_rectangle_gradient_h(streak_x, streak_y, streak_w, streak_h, streak_color, rl.Color(255, 255, 255, 0))

    # Endpoint sparks to make the handle feel animated and "alive".
    endpoint_alpha = int(255 * alpha * (0.06 + 0.2 * energy))
    endpoint_r = max(1, int(1 + 2 * energy))
    rl.draw_circle(int(bar_rect.x + 4), int(bar_rect.y + bar_rect.height / 2), endpoint_r, rl.Color(140, 220, 255, endpoint_alpha))
    rl.draw_circle(int(bar_rect.x + bar_rect.width - 4), int(bar_rect.y + bar_rect.height / 2), endpoint_r, rl.Color(194, 156, 255, endpoint_alpha))

    border_alpha = int(255 * alpha * (0.20 + 0.24 * energy))
    rl.draw_rectangle_rounded_lines_ex(bar_rect, 1.0, 10, 2, rl.Color(38, 65, 95, border_alpha))


class NavWidget(Widget, abc.ABC):
  """
  A full screen widget that supports back navigation by swiping down from the top.
  """
  BACK_TOUCH_AREA_PERCENTAGE = 0.65

  def __init__(self):
    super().__init__()
    self._back_callback: Callable[[], None] | None = None
    self._back_button_start_pos: MousePos | None = None
    self._swiping_away = False  # currently swiping away
    self._can_swipe_away = True  # swipe away is blocked after certain horizontal movement

    self._pos_filter = BounceFilter(0.0, 0.1, 1 / gui_app.target_fps, bounce=1)
    self._playing_dismiss_animation = False
    self._trigger_animate_in = False
    self._nav_bar_show_time = 0.0
    self._back_enabled: bool | Callable[[], bool] = True
    self._nav_bar = NavBar()

    self._nav_bar_y_filter = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)
    self._fx_energy_filter = FirstOrderFilter(0.0, 0.08, 1 / gui_app.target_fps)
    self._intro_t: float | None = None
    self._show_explosion_t: float | None = None

    self._set_up = False

  @property
  def back_enabled(self) -> bool:
    return self._back_enabled() if callable(self._back_enabled) else self._back_enabled

  def set_back_enabled(self, enabled: bool | Callable[[], bool]) -> None:
    self._back_enabled = enabled

  def set_back_callback(self, callback: Callable[[], None]) -> None:
    self._back_callback = callback

  def _handle_mouse_event(self, mouse_event: MouseEvent) -> None:
    super()._handle_mouse_event(mouse_event)

    if not self.back_enabled:
      self._back_button_start_pos = None
      self._swiping_away = False
      self._can_swipe_away = True
      return

    if mouse_event.left_pressed:
      # user is able to swipe away if starting near top of screen, or anywhere if scroller is at top
      self._pos_filter.update_alpha(0.04)
      in_dismiss_area = mouse_event.pos.y < self._rect.height * self.BACK_TOUCH_AREA_PERCENTAGE

      scroller_at_top = False
      vertical_scroller = False
      # TODO: -20? snapping in WiFi dialog can make offset not be positive at the top
      if hasattr(self, '_scroller'):
        scroller_at_top = self._scroller.scroll_panel.get_offset() >= -20 and not self._scroller._horizontal
        vertical_scroller = not self._scroller._horizontal
      elif hasattr(self, '_scroll_panel'):
        scroller_at_top = self._scroll_panel.get_offset() >= -20 and not self._scroll_panel._horizontal
        vertical_scroller = not self._scroll_panel._horizontal

      # Vertical scrollers need to be at the top to swipe away to prevent erroneous swipes
      if (not vertical_scroller and in_dismiss_area) or scroller_at_top:
        self._can_swipe_away = True
        self._back_button_start_pos = mouse_event.pos

    elif mouse_event.left_down:
      if self._back_button_start_pos is not None:
        # block swiping away if too much horizontal or upward movement
        horizontal_movement = abs(mouse_event.pos.x - self._back_button_start_pos.x) > BLOCK_SWIPE_AWAY_THRESHOLD
        upward_movement = mouse_event.pos.y - self._back_button_start_pos.y < -BLOCK_SWIPE_AWAY_THRESHOLD
        if not self._swiping_away and (horizontal_movement or upward_movement):
          self._can_swipe_away = False
          self._back_button_start_pos = None

        # block horizontal swiping if now swiping away
        if self._can_swipe_away:
          if mouse_event.pos.y - self._back_button_start_pos.y > START_DISMISSING_THRESHOLD:
            self._swiping_away = True

    elif mouse_event.left_released:
      self._pos_filter.update_alpha(0.1)
      # if far enough, trigger back navigation callback
      if self._back_button_start_pos is not None:
        if mouse_event.pos.y - self._back_button_start_pos.y > SWIPE_AWAY_THRESHOLD:
          self._playing_dismiss_animation = True

      self._back_button_start_pos = None
      self._swiping_away = False

  def _update_state(self):
    super()._update_state()

    # Disable self's scroller while swiping away
    if not self._set_up:
      self._set_up = True
      if hasattr(self, '_scroller'):
        original_enabled = self._scroller._enabled
        self._scroller.set_enabled(lambda: not self._swiping_away and (original_enabled() if callable(original_enabled) else
                                                                       original_enabled))
      elif hasattr(self, '_scroll_panel'):
        original_enabled = self._scroll_panel.enabled
        self._scroll_panel.set_enabled(lambda: not self._swiping_away and (original_enabled() if callable(original_enabled) else
                                                                          original_enabled))

    if self._trigger_animate_in:
      self._pos_filter.x = self._rect.height + 54
      self._pos_filter.velocity.x = -52
      self._pos_filter.bounce = 1.16
      self._nav_bar_y_filter.x = -NAV_BAR_MARGIN - NAV_BAR_HEIGHT
      self._nav_bar_show_time = rl.get_time()
      self._intro_t = rl.get_time()
      self._show_explosion_t = self._intro_t
      self._trigger_animate_in = False

    new_y = 0.0

    if self._back_button_start_pos is not None:
      last_mouse_event = gui_app.last_mouse_event
      # push entire widget as user drags it away
      new_y = max(last_mouse_event.pos.y - self._back_button_start_pos.y, 0)
      if new_y < SWIPE_AWAY_THRESHOLD:
        new_y /= 2  # resistance until mouse release would dismiss widget

    if self._swiping_away:
      self._nav_bar.set_alpha(1.0)

    if self._playing_dismiss_animation:
      new_y = self._rect.height + DISMISS_PUSH_OFFSET

    new_y = round(self._pos_filter.update(new_y))
    if abs(new_y) < 1 and self._pos_filter.velocity.x == 0.0:
      new_y = self._pos_filter.x = 0.0

    if new_y > self._rect.height + DISMISS_PUSH_OFFSET - 10:
      if self._back_callback is not None:
        self._back_callback()

      self._playing_dismiss_animation = False
      self._back_button_start_pos = None
      self._swiping_away = False

    drag_progress = min(1.0, max(0.0, new_y / max(1.0, SWIPE_AWAY_THRESHOLD * 1.35)))
    motion_energy = min(1.0, abs(self._pos_filter.velocity.x) / 1000.0)
    if self._swiping_away:
      motion_energy = max(motion_energy, 0.5)
    if self._playing_dismiss_animation:
      motion_energy = max(motion_energy, 0.85)
    self._nav_bar.set_drag_progress(drag_progress)
    self._nav_bar.set_energy(motion_energy)
    intro_boost = 0.0
    if self._intro_t is not None:
      intro_dt = rl.get_time() - self._intro_t
      if intro_dt < NAV_INTRO_BOUNCE_TIME:
        intro_boost = (1.0 - intro_dt / NAV_INTRO_BOUNCE_TIME) ** 1.4
      else:
        self._intro_t = None
        self._pos_filter.bounce = 1.0
    self._fx_energy_filter.update(max(motion_energy, drag_progress * 0.72, intro_boost))

    self.set_position(self._rect.x, new_y)

  def render(self, rect: rl.Rectangle | None = None) -> bool | int | None:
    ret = super().render(rect)
    t = rl.get_time()

    # Bottom launch explosion when widget shows.
    if self._show_explosion_t is not None:
      dt = t - self._show_explosion_t
      if dt > NAV_SHOW_EXPLOSION_DURATION:
        self._show_explosion_t = None
      else:
        p = max(0.0, min(1.0, dt / NAV_SHOW_EXPLOSION_DURATION))
        fade = (1.0 - p)
        origin_x = self._rect.x + self._rect.width / 2
        origin_y = self._rect.y + self._rect.height + 2

        base_alpha = int(255 * 0.24 * (fade ** 1.2))
        rl.draw_circle_gradient(int(origin_x), int(origin_y - 4), int(52 + 135 * p),
                                rl.Color(130, 210, 255, base_alpha),
                                rl.Color(130, 210, 255, 0))
        shock_alpha = int(255 * 0.33 * (fade ** 1.35))
        rl.draw_circle_lines(int(origin_x), int(origin_y), 30 + 230 * p, rl.Color(166, 226, 255, shock_alpha))

        for i in range(NAV_SHOW_EXPLOSION_PARTICLES):
          seed = i * 0.77
          ang = -math.pi / 2 + (i / max(1, NAV_SHOW_EXPLOSION_PARTICLES - 1) - 0.5) * 1.9 + math.sin(seed * 1.6) * 0.08
          speed = 90 + 230 * (0.35 + 0.65 * ((math.sin(seed * 2.3) + 1.0) * 0.5))
          px = origin_x + math.cos(ang) * speed * p
          py = origin_y + math.sin(ang) * speed * p - 24 * p * (1.0 - p)
          pa = int(255 * (0.12 + 0.42 * fade) * (0.6 + 0.4 * math.sin(seed * 3.1 + t * 12.0)))
          pr = 1 + int(2.4 * (1.0 - p))
          if i % 2 == 0:
            pc = rl.Color(158, 224, 255, min(255, max(0, pa)))
          else:
            pc = rl.Color(198, 156, 255, min(255, max(0, pa)))
          rl.draw_circle(int(px), int(py), pr, pc)

    if self.back_enabled:
      fx_energy = self._fx_energy_filter.x
      bar_x = self._rect.x + (self._rect.width - self._nav_bar.rect.width) / 2
      nav_bar_delayed = rl.get_time() - self._nav_bar_show_time < 0.4
      # User dragging or dismissing, nav bar follows NavWidget
      if self._back_button_start_pos is not None or self._playing_dismiss_animation:
        self._nav_bar_y_filter.x = NAV_BAR_MARGIN + self._pos_filter.x
      # Waiting to show
      elif nav_bar_delayed:
        self._nav_bar_y_filter.x = -NAV_BAR_MARGIN - NAV_BAR_HEIGHT
      # Animate back to top
      else:
        self._nav_bar_y_filter.update(NAV_BAR_MARGIN)

      # Draw rich backdrop above widget while dismissing.
      if self._rect.y > 0:
        top_h = int(self._rect.y)
        rl.draw_rectangle(int(self._rect.x), 0, int(self._rect.width), top_h, rl.Color(6, 8, 14, 255))
        rl.draw_rectangle_gradient_v(int(self._rect.x), 0, int(self._rect.width), top_h,
                                     rl.Color(112, 186, 255, min(255, int(NAV_EPIC_AURA_MAX_ALPHA * fx_energy))),
                                     rl.Color(0, 0, 0, 0))

      # Aura around top edge of moving panel (alive energy ribbon).
      if fx_energy > 0.01:
        edge_glow_h = int(10 + 22 * fx_energy)
        edge_alpha = min(255, int(255 * (0.06 + 0.26 * fx_energy)))
        rl.draw_rectangle_gradient_v(int(self._rect.x), int(self._rect.y),
                                     int(self._rect.width), edge_glow_h,
                                     rl.Color(124, 206, 255, edge_alpha), rl.Color(124, 206, 255, 0))
        rl.draw_rectangle_gradient_h(int(self._rect.x), int(self._rect.y),
                                     int(self._rect.width), edge_glow_h // 2,
                                     rl.Color(135, 220, 255, int(edge_alpha * 0.55)),
                                     rl.Color(188, 142, 255, int(edge_alpha * 0.55)))

        # Motion particles near nav bar.
        bar_center_x = bar_x + self._nav_bar.rect.width / 2
        bar_y = self._nav_bar_y_filter.x + NAV_BAR_HEIGHT / 2
        particle_count = NAV_EPIC_PARTICLE_COUNT + (NAV_INTRO_PARTICLE_BOOST if self._intro_t is not None else 0)
        for i in range(particle_count):
          p_phase = t * (2.8 + 0.45 * i + 1.4 * fx_energy) + i * 1.47
          px = bar_center_x + math.sin(p_phase * 0.82) * (18 + 36 * fx_energy)
          py = bar_y + math.cos(p_phase * 1.21) * (4 + 10 * fx_energy)
          p_alpha = int(255 * (0.08 + 0.20 * fx_energy) * (0.45 + 0.55 * (0.5 + 0.5 * math.sin(p_phase * 1.7))))
          pr = 1 + int(2 * fx_energy)
          rl.draw_circle(int(px), int(py), pr, rl.Color(168, 228, 255, min(255, p_alpha)))

        # Intro-only ribbon trails to emphasize physical launch-in.
        if self._intro_t is not None:
          trail_alpha = min(255, int(255 * 0.22 * fx_energy))
          for i in range(5):
            off = i * 7
            rl.draw_rectangle_gradient_v(int(self._rect.x), int(self._rect.y - off), int(self._rect.width), 6,
                                         rl.Color(132, 214, 255, trail_alpha // (i + 1)),
                                         rl.Color(132, 214, 255, 0))

      self._nav_bar.set_position(bar_x, round(self._nav_bar_y_filter.x))
      self._nav_bar.render()

    return ret

  def show_event(self):
    super().show_event()
    # FIXME: we don't know the height of the rect at first show_event since it's before the first render :(
    #  so we need this hacky bool for now
    self._trigger_animate_in = True
    self._nav_bar.show_event()
