import pyray as rl
import numpy as np
from collections.abc import Callable

from openpilot.common.filter_simple import FirstOrderFilter, BounceFilter
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2, ScrollState
from openpilot.system.ui.widgets import Widget

ITEM_SPACING = 20
LINE_COLOR = rl.GRAY
LINE_PADDING = 40
ANIMATION_SCALE = 0.6

EDGE_SHADOW_WIDTH = 20

MIN_ZOOM_ANIMATION_TIME = 0.075  # seconds
DO_ZOOM = True
DO_JELLO = True
JELLO_INTENSITY = 18  # drive strength from scroll speed

# Carousel depth: stronger center pop with smaller edges
CAROUSEL_SCALE_RANGE = (0.86, 1.07)   # edge -> center
CAROUSEL_FALLOFF = 230  # px from center where effect maxes out
CENTER_PULSE_AMPLITUDE = 0.010        # reduced pulse to avoid persistent shake
CENTER_PULSE_HZ = 2.2                 # slightly slower pulse speed

# Real jello spring model (mass-spring-damper).
JELLO_SPRING_K = 130.0
JELLO_DAMPING = 24.0
JELLO_MAX_OFFSET = 34.0
JELLO_STRETCH_MAX = 0.14
JELLO_VEL_TO_STRETCH = 1800.0
STRETCH_SMOOTH_ALPHA = 0.26
STRETCH_AXIS_SMOOTH_ALPHA = 0.18
STRETCH_DIRECTION_DEADZONE = 90.0  # px/s

# Horizontal-only stretch tuning (vertical behavior remains unchanged).
HORIZONTAL_STRETCH_MAX = 0.10
HORIZONTAL_STRETCH_SMOOTH_ALPHA = 0.18
HORIZONTAL_STRETCH_AXIS_SMOOTH_ALPHA = 0.12
HORIZONTAL_STRETCH_DIRECTION_DEADZONE = 130.0
HORIZONTAL_RELEASE_BOUNCE_GAIN = 0.0017

# Color/sparkle accents for a lively feel without being distracting.
SPARKLE_COUNT = 8
SPARKLE_BASE_ALPHA = 0.06
SPARKLE_ENERGY_ALPHA = 0.13
LIQUID_GLASS_BASE_ALPHA = 0.12
LIQUID_GLASS_ENERGY_ALPHA = 0.20
LIQUID_GLASS_SWEEP_HZ = 4.1
SCROLLER_BG_AMBIENT_ALPHA = 0.045


class LineSeparator(Widget):
  def __init__(self, height: int = 1):
    super().__init__()
    self._rect = rl.Rectangle(0, 0, 0, height)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._rect.width = parent_rect.width

  def _render(self, _):
    rl.draw_line(int(self._rect.x) + LINE_PADDING, int(self._rect.y),
                 int(self._rect.x + self._rect.width) - LINE_PADDING, int(self._rect.y),
                 LINE_COLOR)


class ScrollIndicator(Widget):
  HORIZONTAL_MARGIN = 4

  def __init__(self):
    super().__init__()
    self._txt_scroll_indicator = gui_app.texture("icons_mici/settings/horizontal_scroll_indicator.png", 96, 48)
    self._scroll_offset: float = 0.0
    self._content_size: float = 0.0
    self._viewport: rl.Rectangle = rl.Rectangle(0, 0, 0, 0)
    self._is_active: bool = False
    self._x_filter = FirstOrderFilter(0.0, 0.09, 1 / gui_app.target_fps)
    self._w_filter = FirstOrderFilter(self._txt_scroll_indicator.width, 0.11, 1 / gui_app.target_fps)
    self._initialized = False

  def update(self, scroll_offset: float, content_size: float, viewport: rl.Rectangle,
             is_active: bool = False) -> None:
    self._scroll_offset = scroll_offset
    self._content_size = content_size
    self._viewport = viewport
    self._is_active = is_active

  def _render(self, _):
    # scale indicator width based on content size
    indicator_w = float(np.interp(self._content_size, [1000, 3000], [300, 100]))

    # position based on scroll ratio
    slide_range = self._viewport.width - indicator_w
    max_scroll = max(1.0, self._content_size - self._viewport.width)
    scroll_ratio = -self._scroll_offset / max_scroll
    x = self._viewport.x + scroll_ratio * slide_range
    # don't bounce up when NavWidget shows
    y = max(self._viewport.y, 0) + self._viewport.height - self._txt_scroll_indicator.height / 2

    # Smoothly squeeze when overscrolling past edges.
    viewport_left = self._viewport.x
    viewport_right = self._viewport.x + self._viewport.width
    overscroll_left = max(viewport_left - x, 0.0)
    overscroll_right = max((x + indicator_w) - viewport_right, 0.0)
    overscroll = overscroll_left + overscroll_right
    squish = min(0.5, overscroll / max(indicator_w, 1.0))

    # Keep a minimum width while still feeling elastic.
    target_w = max(indicator_w * 0.52, indicator_w * (1.0 - squish))
    target_center = x + indicator_w / 2

    if self._is_active:
      # Add wobble, but suppress it when heavily squished near edges to prevent jerk.
      wobble_mix = 1.0 - min(1.0, squish * 1.8)
      wobble = 1.0 + 0.08 * wobble_mix * np.sin(rl.get_time() * 13.0)
      target_w *= wobble

    # Low-pass x/width to avoid edge jitter during rapid gesture changes.
    if not self._initialized:
      self._x_filter.x = target_center
      self._w_filter.x = target_w
      self._initialized = True
    else:
      self._x_filter.update(target_center)
      self._w_filter.update(target_w)

    dest_w = self._w_filter.x
    dest_left = self._x_filter.x - dest_w / 2
    dest_left = min(dest_left, viewport_right - dest_w)
    dest_left = max(dest_left, viewport_left)

    # pulse alpha when actively scrolling - feels alive and responsive
    base_alpha = 0.45
    alpha = 0.7 if self._is_active else base_alpha

    src_rec = rl.Rectangle(0, 0, self._txt_scroll_indicator.width, self._txt_scroll_indicator.height)
    dest_rec = rl.Rectangle(dest_left, y, dest_w, self._txt_scroll_indicator.height)
    rl.draw_texture_pro(self._txt_scroll_indicator, src_rec, dest_rec, rl.Vector2(0, 0), 0.0,
                        rl.Color(255, 255, 255, int(255 * alpha)))


class Scroller(Widget):
  def __init__(self, items: list[Widget], horizontal: bool = True, snap_items: bool = True, spacing: int = ITEM_SPACING,
               line_separator: bool = False, pad_start: int = ITEM_SPACING, pad_end: int = ITEM_SPACING,
               scroll_indicator: bool = True, edge_shadows: bool = True):
    super().__init__()
    self._items: list[Widget] = []
    self._horizontal = horizontal
    self._snap_items = snap_items
    self._spacing = spacing
    self._line_separator = LineSeparator() if line_separator else None
    self._pad_start = pad_start
    self._pad_end = pad_end

    self._reset_scroll_at_show = True

    self._scrolling_to: float | None = None
    self._scroll_filter = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)
    self._zoom_filter = FirstOrderFilter(1.0, 0.2, 1 / gui_app.target_fps)
    self._zoom_out_t: float = 0.0
    self._dt = 1 / gui_app.target_fps

    # layout state
    self._visible_items: list[Widget] = []
    self._content_size: float = 0.0
    self._scroll_offset: float = 0.0
    self._prev_scroll_offset: float = 0.0
    self._scroll_velocity = FirstOrderFilter(0.0, 0.09, self._dt)

    self._item_pos_filter = BounceFilter(0.0, 0.05, 1 / gui_app.target_fps)
    # Per-item physical spring state: {id(item): {"pos": float, "vel": float}}
    self._jello_item_state: dict[int, dict[str, float]] = {}

    # when not pressed, snap to closest item to center
    # horizontal gets a slightly springier settle so release feels less dead.
    if self._horizontal:
      self._scroll_snap_filter = BounceFilter(0.0, 0.07, 1 / gui_app.target_fps, bounce=1.42)
    else:
      self._scroll_snap_filter = FirstOrderFilter(0.0, 0.05, 1 / gui_app.target_fps)
    self._prev_scroll_panel_state = ScrollState.STEADY

    self.scroll_panel = GuiScrollPanel2(self._horizontal, handle_out_of_bounds=not self._snap_items)
    self._scroll_enabled: bool | Callable[[], bool] = True

    self._show_scroll_indicator = scroll_indicator and self._horizontal
    self._scroll_indicator = ScrollIndicator()
    self._edge_shadows = edge_shadows and self._horizontal

    for item in items:
      self.add_widget(item)

  def set_reset_scroll_at_show(self, scroll: bool):
    self._reset_scroll_at_show = scroll

  def scroll_to(self, pos: float, smooth: bool = False):
    # already there
    if abs(pos) < 1:
      return

    # FIXME: the padding correction doesn't seem correct
    scroll_offset = self.scroll_panel.get_offset() - pos
    if smooth:
      self._scrolling_to = scroll_offset
    else:
      self.scroll_panel.set_offset(scroll_offset)

  @property
  def is_auto_scrolling(self) -> bool:
    return self._scrolling_to is not None

  def add_widget(self, item: Widget) -> None:
    self._items.append(item)
    item.set_touch_valid_callback(lambda: self.scroll_panel.is_touch_valid() and self.enabled)

  def set_scrolling_enabled(self, enabled: bool | Callable[[], bool]) -> None:
    """Set whether scrolling is enabled (does not affect widget enabled state)."""
    self._scroll_enabled = enabled

  def _update_state(self):
    if DO_ZOOM:
      if self._scrolling_to is not None or self.scroll_panel.state != ScrollState.STEADY:
        self._zoom_out_t = rl.get_time() + MIN_ZOOM_ANIMATION_TIME
        self._zoom_filter.update(0.92)
      else:
        if self._zoom_out_t is not None:
          if rl.get_time() > self._zoom_out_t:
            self._zoom_filter.update(1.0)
          else:
            self._zoom_filter.update(0.92)

    # Cancel auto-scroll if user starts manually scrolling
    if self._scrolling_to is not None and (self.scroll_panel.state == ScrollState.PRESSED or self.scroll_panel.state == ScrollState.MANUAL_SCROLL):
      self._scrolling_to = None

    if self._scrolling_to is not None:
      self._scroll_filter.update(self._scrolling_to)
      self.scroll_panel.set_offset(self._scroll_filter.x)

      if abs(self._scroll_filter.x - self._scrolling_to) < 1:
        self.scroll_panel.set_offset(self._scrolling_to)
        self._scrolling_to = None
    else:
      # keep current scroll position up to date
      self._scroll_filter.x = self.scroll_panel.get_offset()

  def _get_scroll(self, visible_items: list[Widget], content_size: float) -> float:
    scroll_enabled = self._scroll_enabled() if callable(self._scroll_enabled) else self._scroll_enabled
    self.scroll_panel.set_enabled(scroll_enabled and self.enabled)
    self.scroll_panel.update(self._rect, content_size)
    panel_state = self.scroll_panel.state
    if not self._snap_items:
      self._prev_scroll_panel_state = panel_state
      return round(self.scroll_panel.get_offset())

    if self._horizontal and panel_state == ScrollState.AUTO_SCROLL and \
       self._prev_scroll_panel_state in (ScrollState.PRESSED, ScrollState.MANUAL_SCROLL):
      if isinstance(self._scroll_snap_filter, BounceFilter):
        release_v = float(np.clip(self._scroll_velocity.x, -2800.0, 2800.0))
        self._scroll_snap_filter.velocity.x = release_v * HORIZONTAL_RELEASE_BOUNCE_GAIN

    # Snap closest item to center.
    center_pos = self._rect.x + self._rect.width / 2 if self._horizontal else self._rect.y + self._rect.height / 2
    cur_offset = self.scroll_panel.get_offset()
    closest_delta_pos = float('inf')
    snap_item_center: float | None = None
    cur_pos = 0.0
    for idx, item in enumerate(visible_items):
      if self._horizontal:
        # Horizontal: compute centers from stable content layout model (not item.rect),
        # since item.rect can be jello-transformed and causes snap-target jitter/fighting.
        spacing = self._spacing if idx > 0 else self._pad_start
        item_center = self._rect.x + cur_pos + spacing + item.rect.width / 2 + cur_offset
        cur_pos += item.rect.width + spacing
      else:
        # Vertical: preserve original behavior.
        item_center = item.rect.y + item.rect.height / 2

      delta_pos = item_center - center_pos
      if abs(delta_pos) < abs(closest_delta_pos):
        closest_delta_pos = delta_pos
        snap_item_center = item_center

    if snap_item_center is not None:
      if self.is_pressed:
        # no snapping until released
        self._scroll_snap_filter.x = 0
      else:
        # TODO: this doesn't handle two small buttons at the edges well
        if self._horizontal:
          # Horizontal: keep trying to snap after release too (AUTO_SCROLL), but
          # scale snap strength by current speed to avoid fighting momentum.
          if panel_state in (ScrollState.PRESSED, ScrollState.MANUAL_SCROLL):
            self._scroll_snap_filter.x = 0
            self._prev_scroll_panel_state = panel_state
            return self.scroll_panel.get_offset()

          speed = abs(self._scroll_velocity.x)
          vel = self._scroll_velocity.x
          speed_t = min(1.0, speed / 2200.0)
          # High speed => weaker snap; low speed => stronger snap.
          snap_divisor = 13.0 + 14.0 * speed_t
          snap_delta_pos = (center_pos - snap_item_center) / snap_divisor
          snap_delta_pos = min(snap_delta_pos, -cur_offset / snap_divisor)
          snap_delta_pos = max(snap_delta_pos, (self._rect.width - cur_offset - content_size) / snap_divisor)
          if panel_state == ScrollState.AUTO_SCROLL:
            # Prevent tug-of-war: while momentum is still high, only allow snap assist
            # if it helps current travel direction. Otherwise, wait until velocity drops.
            opposing_momentum = (snap_delta_pos * vel) < 0.0 and speed > 520.0
            if opposing_momentum:
              snap_delta_pos = 0.0
              self._scroll_snap_filter.x = 0.0
            else:
              snap_delta_pos *= (0.14 + 0.86 * (1.0 - speed_t))
          # Clamp per-frame snap displacement; permit larger settle steps at low speed.
          snap_clip = 4.0 + 8.0 * (1.0 - speed_t)
          snap_delta_pos = np.clip(snap_delta_pos, -snap_clip, snap_clip)
        else:
          snap_delta_pos = (center_pos - snap_item_center) / 10
          snap_delta_pos = min(snap_delta_pos, -cur_offset / 10)
          snap_delta_pos = max(snap_delta_pos, (self._rect.height - cur_offset - content_size) / 10)
        self._scroll_snap_filter.update(snap_delta_pos)

      self.scroll_panel.set_offset(cur_offset + self._scroll_snap_filter.x)

    self._prev_scroll_panel_state = panel_state
    return self.scroll_panel.get_offset()

  def _layout(self):
    self._visible_items = [item for item in self._items if item.is_visible]

    # Add line separator between items
    if self._line_separator is not None:
      l = len(self._visible_items)
      for i in range(1, len(self._visible_items)):
        self._visible_items.insert(l - i, self._line_separator)

    self._content_size = sum(item.rect.width if self._horizontal else item.rect.height for item in self._visible_items)
    self._content_size += self._spacing * (len(self._visible_items) - 1)
    self._content_size += self._pad_start + self._pad_end

    self._scroll_offset = self._get_scroll(self._visible_items, self._content_size)
    raw_scroll_velocity = (self._scroll_offset - self._prev_scroll_offset) / self._dt
    self._scroll_velocity.update(raw_scroll_velocity)
    self._prev_scroll_offset = self._scroll_offset

    self._item_pos_filter.update(self._scroll_offset)
    visible_item_ids = {id(item) for item in self._visible_items}
    self._jello_item_state = {k: v for k, v in self._jello_item_state.items() if k in visible_item_ids}

    cur_pos = 0
    for idx, item in enumerate(self._visible_items):
      spacing = self._spacing if (idx > 0) else self._pad_start
      # Nicely lay out items horizontally/vertically
      if self._horizontal:
        x = self._rect.x + cur_pos + spacing
        y = self._rect.y + (self._rect.height - item.rect.height) / 2
        cur_pos += item.rect.width + spacing
      else:
        x = self._rect.x + (self._rect.width - item.rect.width) / 2
        y = self._rect.y + cur_pos + spacing
        cur_pos += item.rect.height + spacing

      # Consider scroll
      if self._horizontal:
        x += self._scroll_offset
      else:
        y += self._scroll_offset

      # Real jello physics: per-item spring follows target with damping and velocity drive.
      if DO_JELLO:
        primary_target = x if self._horizontal else y
        item_key = id(item)
        spring = self._jello_item_state.get(item_key)
        if spring is None:
          spring = {"pos": primary_target, "vel": 0.0}
          self._jello_item_state[item_key] = spring

        if self._horizontal:
          center = self._rect.x + self._rect.width / 2
          item_center = x + item.rect.width / 2
          edge_norm = min(1.0, abs(item_center - center) / max(1.0, self._rect.width / 2))
        else:
          center = self._rect.y + self._rect.height / 2
          item_center = y + item.rect.height / 2
          edge_norm = min(1.0, abs(item_center - center) / max(1.0, self._rect.height / 2))

        drive = np.clip(self._scroll_velocity.x / 2200.0, -1.5, 1.5) * JELLO_INTENSITY * (0.65 + 0.7 * edge_norm)
        accel = JELLO_SPRING_K * (primary_target - spring["pos"]) - JELLO_DAMPING * spring["vel"] + drive
        spring["vel"] += accel * self._dt
        spring["pos"] += spring["vel"] * self._dt
        jello_delta = np.clip(spring["pos"] - primary_target, -JELLO_MAX_OFFSET, JELLO_MAX_OFFSET)

        if self._horizontal:
          x = primary_target + jello_delta
        else:
          y = primary_target + jello_delta

      # Update item state
      item.set_position(round(x), round(y))  # round to prevent jumping when settling
      item.set_parent_rect(self._rect)

  def _render(self, _):
    rl.begin_scissor_mode(int(self._rect.x), int(self._rect.y),
                          int(self._rect.width), int(self._rect.height))

    # Subtle ambient backdrop inside scroller viewport.
    t = rl.get_time()
    bg_a = int(255 * SCROLLER_BG_AMBIENT_ALPHA)
    ambient_rect = rl.Rectangle(self._rect.x + 5, self._rect.y + 4, self._rect.width - 10, self._rect.height - 8)
    ambient_roundness = min(1.0, 22 / max(1.0, min(ambient_rect.width, ambient_rect.height) / 2))
    rl.draw_rectangle_rounded(ambient_rect, ambient_roundness, 12, rl.Color(92, 146, 232, int(bg_a * 0.85)))
    rl.draw_rectangle_rounded_lines_ex(ambient_rect, ambient_roundness, 12, 1, rl.Color(165, 212, 255, int(bg_a * 0.75)))
    # Soft drifting blobs for depth (kept intentionally faint).
    blob_a = int(255 * SCROLLER_BG_AMBIENT_ALPHA * 0.65)
    blob_r = max(18, int(min(self._rect.width, self._rect.height) * 0.14))
    bx1 = self._rect.x + self._rect.width * (0.25 + 0.12 * np.sin(t * 0.42))
    by1 = self._rect.y + self._rect.height * (0.35 + 0.10 * np.cos(t * 0.37))
    bx2 = self._rect.x + self._rect.width * (0.72 + 0.10 * np.cos(t * 0.33 + 1.2))
    by2 = self._rect.y + self._rect.height * (0.62 + 0.08 * np.sin(t * 0.45 + 0.8))
    rl.draw_circle_gradient(int(bx1), int(by1), float(blob_r), rl.Color(140, 205, 255, blob_a), rl.Color(140, 205, 255, 0))
    rl.draw_circle_gradient(int(bx2), int(by2), float(blob_r * 1.1), rl.Color(176, 150, 255, blob_a), rl.Color(176, 150, 255, 0))

    for item in reversed(self._visible_items):
      # Skip rendering if not in viewport
      if not rl.check_collision_recs(item.rect, self._rect):
        continue

      # Carousel depth: scale down items toward the edges for a living, dimensional feel
      if self._horizontal:
        viewport_center = self._rect.x + self._rect.width / 2
        item_center = item.rect.x + item.rect.width / 2
      else:
        viewport_center = self._rect.y + self._rect.height / 2
        item_center = item.rect.y + item.rect.height / 2
      dist_from_center = abs(item_center - viewport_center)
      center_t = min(1.0, dist_from_center / CAROUSEL_FALLOFF)
      carousel_scale = np.interp(center_t, [0, 1], [CAROUSEL_SCALE_RANGE[1], CAROUSEL_SCALE_RANGE[0]])
      # Tiny center pulse gives an "alive" feel even at low speed.
      center_weight = 1.0 - center_t
      speed_energy = min(1.0, abs(self._scroll_velocity.x) / 2200.0)
      interaction_boost = 0.0
      if self.scroll_panel.state in (ScrollState.PRESSED, ScrollState.MANUAL_SCROLL, ScrollState.AUTO_SCROLL):
        interaction_boost += 0.16
      if self.is_pressed:
        interaction_boost += 0.08
      glow_energy = min(1.0, speed_energy + interaction_boost)
      # Keep a very light idle pulse, stronger only while moving.
      pulse_strength = CENTER_PULSE_AMPLITUDE * (0.18 + 0.82 * glow_energy)
      pulse = 1.0 + pulse_strength * center_weight * np.sin(rl.get_time() * (2 * np.pi * CENTER_PULSE_HZ))

      # Combine with zoom filter (when DO_ZOOM enabled)
      base_scale = self._zoom_filter.x * carousel_scale * pulse
      scale_x = base_scale
      scale_y = base_scale

      # Stretch/squash follows spring speed (jello-like conservation of volume feel).
      if DO_JELLO:
        spring = self._jello_item_state.get(id(item))
        if spring is not None:
          if self._horizontal:
            stretch_limit = HORIZONTAL_STRETCH_MAX
            stretch_alpha = HORIZONTAL_STRETCH_SMOOTH_ALPHA
            axis_alpha = HORIZONTAL_STRETCH_AXIS_SMOOTH_ALPHA
            axis_deadzone = HORIZONTAL_STRETCH_DIRECTION_DEADZONE
          else:
            stretch_limit = JELLO_STRETCH_MAX
            stretch_alpha = STRETCH_SMOOTH_ALPHA
            axis_alpha = STRETCH_AXIS_SMOOTH_ALPHA
            axis_deadzone = STRETCH_DIRECTION_DEADZONE

          target_stretch = min(stretch_limit, abs(spring["vel"]) / JELLO_VEL_TO_STRETCH)
          stretch = spring.get("stretch", target_stretch)
          stretch += (target_stretch - stretch) * stretch_alpha
          spring["stretch"] = stretch

          # Smooth directional mapping so axis transitions don't flip abruptly.
          vel = self._scroll_velocity.x
          if abs(vel) < axis_deadzone:
            target_axis = 0.0
          else:
            target_axis = float(np.clip(vel / 900.0, -1.0, 1.0))
          axis = spring.get("stretch_axis", target_axis)
          axis += (target_axis - axis) * axis_alpha
          spring["stretch_axis"] = axis

          if self._horizontal:
            # Direction-aware deformation with smooth blend:
            # moving left -> x stretch, moving right -> y stretch.
            anis = abs(axis)
            x_stretch = stretch * ((1.0 - axis) * 0.5) * anis
            y_stretch = stretch * ((1.0 + axis) * 0.5) * anis
            scale_x *= (1.0 + x_stretch) * (1.0 - y_stretch * 0.72)
            scale_y *= (1.0 + y_stretch) * (1.0 - x_stretch * 0.72)
          else:
            scale_x *= (1.0 - stretch * 0.72)
            scale_y *= (1.0 + stretch)

      needs_transform = (scale_x != 1.0 or scale_y != 1.0)
      if needs_transform:
        cx = item.rect.x + item.rect.width / 2
        cy = item.rect.y + item.rect.height / 2
        rl.rl_push_matrix()
        rl.rl_translatef(cx, cy, 0)
        rl.rl_scalef(scale_x, scale_y, 1.0)
        rl.rl_translatef(-cx, -cy, 0)
      item.render()

      # Liquid glass overlay: subtle tint, moving specular sweep, and edge glow.
      if item is not self._line_separator:
        glass_alpha = LIQUID_GLASS_BASE_ALPHA + LIQUID_GLASS_ENERGY_ALPHA * glow_energy

        inset = 2
        glass_rect = rl.Rectangle(item.rect.x + inset, item.rect.y + inset,
                                  max(1, item.rect.width - 2 * inset), max(1, item.rect.height - 2 * inset))
        min_dim = max(1.0, min(glass_rect.width, glass_rect.height))
        corner_px = max(16.0, min(56.0, min_dim * 0.58))
        roundness = min(1.0, corner_px / (min_dim / 2.0))

        # Base frosted tint
        tint = rl.Color(120, 180, 255, int(255 * glass_alpha))
        rl.draw_rectangle_rounded(glass_rect, roundness, 10, tint)

        # Inner depth tint to make glass read stronger
        inner_inset = max(2, int(min_dim * 0.04))
        inner_rect = rl.Rectangle(glass_rect.x + inner_inset, glass_rect.y + inner_inset,
                                  max(1, glass_rect.width - 2 * inner_inset),
                                  max(1, glass_rect.height - 2 * inner_inset))
        inner_tint = rl.Color(145, 198, 255, int(255 * glass_alpha * 0.72))
        rl.draw_rectangle_rounded(inner_rect, roundness, 10, inner_tint)

        gloss_h = max(4, int(glass_rect.height * 0.44))
        gloss_alpha = min(255, int(255 * glass_alpha * 1.45))
        rl.draw_rectangle_gradient_v(int(glass_rect.x), int(glass_rect.y),
                                     int(glass_rect.width), gloss_h,
                                     rl.Color(255, 255, 255, gloss_alpha), rl.Color(255, 255, 255, 0))

        # Bottom bounce light for thicker "glass slab" look
        bounce_h = max(3, int(glass_rect.height * 0.26))
        bounce_y = int(glass_rect.y + glass_rect.height - bounce_h)
        rl.draw_rectangle_gradient_v(int(glass_rect.x), bounce_y, int(glass_rect.width), bounce_h,
                                     rl.Color(170, 215, 255, 0),
                                     rl.Color(170, 215, 255, int(255 * glass_alpha * 0.95)))

        sweep_phase = rl.get_time() * LIQUID_GLASS_SWEEP_HZ + item_center * 0.017
        sweep_x = int(glass_rect.x + glass_rect.width * (0.15 + 0.7 * (0.5 + 0.5 * np.sin(sweep_phase))))
        streak_w = max(8, int(14 + 18 * glow_energy))
        streak_h = max(6, int(glass_rect.height - 6))
        streak_y = int(glass_rect.y + (glass_rect.height - streak_h) / 2)
        streak_color = rl.Color(255, 255, 255, min(255, int(255 * glass_alpha * 1.35)))
        rl.draw_rectangle_gradient_h(sweep_x - streak_w, streak_y, streak_w, streak_h,
                                     rl.Color(255, 255, 255, 0), streak_color)
        rl.draw_rectangle_gradient_h(sweep_x, streak_y, streak_w, streak_h,
                                     streak_color, rl.Color(255, 255, 255, 0))

        # Chromatic edge split for stronger liquid glass character
        edge_main = rl.Color(175, 226, 255, int(255 * (0.18 + 0.30 * glow_energy)))
        edge_cyan = rl.Color(115, 225, 255, int(255 * (0.10 + 0.20 * glow_energy)))
        edge_violet = rl.Color(190, 142, 255, int(255 * (0.09 + 0.18 * glow_energy)))
        rl.draw_rectangle_rounded_lines_ex(glass_rect, roundness, 10, 2, edge_main)
        rl.draw_rectangle_rounded_lines_ex(rl.Rectangle(glass_rect.x - 1, glass_rect.y - 1, glass_rect.width, glass_rect.height),
                                           roundness, 10, 1, edge_cyan)
        rl.draw_rectangle_rounded_lines_ex(rl.Rectangle(glass_rect.x + 1, glass_rect.y + 1, glass_rect.width, glass_rect.height),
                                           roundness, 10, 1, edge_violet)

        # Tiny caustic spark along the sweep.
        caustic_r = max(2, int(2 + 3 * glow_energy))
        caustic_y = int(glass_rect.y + glass_rect.height * (0.32 + 0.25 * np.sin(sweep_phase * 1.37)))
        rl.draw_circle(sweep_x, caustic_y, float(caustic_r),
                       rl.Color(255, 255, 255, min(255, int(255 * glass_alpha * 1.0))))

      if needs_transform:
        rl.rl_pop_matrix()

    # Subtle color sparkles: energy-reactive and bounded to scroller viewport.
    speed_energy = min(1.0, abs(self._scroll_velocity.x) / 2200.0)
    if self.scroll_panel.state in (ScrollState.PRESSED, ScrollState.MANUAL_SCROLL, ScrollState.AUTO_SCROLL):
      speed_energy = min(1.0, speed_energy + 0.16)
    if self._horizontal and len(self._visible_items) > 0:
      t = rl.get_time()
      for i in range(SPARKLE_COUNT):
        phase = t * (1.6 + 0.21 * i) + i * 1.73
        x = self._rect.x + self._rect.width * (0.5 + 0.5 * np.sin(phase * 0.73))
        y = self._rect.y + self._rect.height * (0.18 + 0.64 * (0.5 + 0.5 * np.sin(phase * 1.33 + 1.1)))
        pulse = 0.4 + 0.6 * (0.5 + 0.5 * np.sin(phase * 2.1))

        alpha = SPARKLE_BASE_ALPHA + SPARKLE_ENERGY_ALPHA * speed_energy
        a = int(255 * alpha * pulse)
        size = 1 + int(2 + 4 * speed_energy * pulse)

        # Shift hue cyan -> violet per sparkle phase.
        hue_mix = 0.5 + 0.5 * np.sin(phase * 0.9 + 0.6)
        c1 = rl.Color(85, 220, 255, a)
        c2 = rl.Color(176, 120, 255, a)
        color = rl.Color(int(c1.r + (c2.r - c1.r) * hue_mix),
                         int(c1.g + (c2.g - c1.g) * hue_mix),
                         int(c1.b + (c2.b - c1.b) * hue_mix),
                         a)
        rl.draw_circle(int(x), int(y), float(size), color)

    rl.end_scissor_mode()

    # Draw edge shadows on top of scroller content
    if self._edge_shadows:
      rl.draw_rectangle_gradient_h(int(self._rect.x), int(self._rect.y),
                                   EDGE_SHADOW_WIDTH, int(self._rect.y),
                                   rl.Color(0, 0, 0, 166), rl.BLANK)

      right_x = int(self._rect.x + self._rect.width - EDGE_SHADOW_WIDTH)
      rl.draw_rectangle_gradient_h(right_x, int(self._rect.y),
                                   EDGE_SHADOW_WIDTH, int(self._rect.y),
                                   rl.BLANK, rl.Color(0, 0, 0, 166))

    # Draw scroll indicator on top of edge shadows
    if self._show_scroll_indicator and len(self._visible_items) > 0:
      is_scrolling = (self.scroll_panel.state != ScrollState.STEADY or
                      self._scrolling_to is not None)
      self._scroll_indicator.update(self._scroll_offset, self._content_size, self._rect,
                                    is_active=is_scrolling)
      self._scroll_indicator.render()

  def show_event(self):
    super().show_event()
    if self._reset_scroll_at_show:
      self.scroll_panel.set_offset(0.0)
    self._prev_scroll_offset = self.scroll_panel.get_offset()
    self._scroll_velocity.x = 0.0
    self._jello_item_state.clear()

    for item in self._items:
      item.show_event()

  def hide_event(self):
    super().hide_event()
    for item in self._items:
      item.hide_event()
