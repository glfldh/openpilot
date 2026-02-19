import math
import random
import numpy as np
import pyray as rl
from collections.abc import Callable

from openpilot.common.swaglog import cloudlog
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.selfdrive.ui.mici.widgets.dialog import BigMultiOptionDialog, BigInputDialog, BigDialogOptionButton, BigConfirmationDialogV2
from openpilot.system.ui.lib.application import gui_app, MousePos, FontWeight
from openpilot.system.ui.widgets import Widget, NavWidget
from openpilot.system.ui.lib.wifi_manager import WifiManager, Network, SecurityType, WifiState
from openpilot.common.filter_simple import FirstOrderFilter


def normalize_ssid(ssid: str) -> str:
  return ssid.replace("’", "'")  # for iPhone hotspots


class LoadingAnimation(Widget):
  def _render(self, _):
    cx = int(self._rect.x + 70)
    cy = int(self._rect.y + self._rect.height / 2 - 50)

    y_mag = 20
    anim_scale = 5
    spacing = 28

    for i in range(3):
      x = cx - spacing + i * spacing
      y = int(cy + min(math.sin((rl.get_time() - i * 0.2) * anim_scale) * y_mag, 0))
      alpha = int(np.interp(cy - y, [0, y_mag], [255 * 0.45, 255 * 0.9]))
      rl.draw_circle(x, y, 10, rl.Color(255, 255, 255, alpha))


class WifiIcon(Widget):
  def __init__(self):
    super().__init__()
    self.set_rect(rl.Rectangle(0, 0, 86, 64))

    self._wifi_slash_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_slash.png", 86, 64)
    self._wifi_low_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_low.png", 86, 64)
    self._wifi_medium_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_medium.png", 86, 64)
    self._wifi_full_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_full.png", 86, 64)
    self._lock_txt = gui_app.texture("icons_mici/settings/network/new/lock.png", 22, 32)

    self._network: Network | None = None
    self._network_missing = False  # if network disappeared from scan results
    self._scale = 1.0
    self._opacity = 1.0

  def set_current_network(self, network: Network):
    self._network = network

  def set_network_missing(self, missing: bool):
    self._network_missing = missing

  def set_scale(self, scale: float):
    self._scale = scale

  def set_opacity(self, opacity: float):
    self._opacity = opacity

  @staticmethod
  def get_strength_icon_idx(strength: int) -> int:
    return round(strength / 100 * 2)

  def _render(self, _):
    if self._network is None:
      return

    # Determine which wifi strength icon to use
    strength = self.get_strength_icon_idx(self._network.strength)
    if self._network_missing:
      strength_icon = self._wifi_slash_txt
    elif strength == 2:
      strength_icon = self._wifi_full_txt
    elif strength == 1:
      strength_icon = self._wifi_medium_txt
    else:
      strength_icon = self._wifi_low_txt

    tint = rl.Color(255, 255, 255, int(255 * self._opacity))
    icon_x = int(self._rect.x + (self._rect.width - strength_icon.width * self._scale) // 2)
    icon_y = int(self._rect.y + (self._rect.height - strength_icon.height * self._scale) // 2)
    rl.draw_texture_ex(strength_icon, (icon_x, icon_y), 0.0, self._scale, tint)

    # Render lock icon at lower right of wifi icon if secured
    if self._network.security_type not in (SecurityType.OPEN, SecurityType.UNSUPPORTED):
      lock_scale = self._scale * 1.1
      lock_x = int(icon_x + 1 + strength_icon.width * self._scale - self._lock_txt.width * lock_scale / 2)
      lock_y = int(icon_y + 1 + strength_icon.height * self._scale - self._lock_txt.height * lock_scale / 2)
      rl.draw_texture_ex(self._lock_txt, (lock_x, lock_y), 0.0, lock_scale, tint)


class WifiItem(BigDialogOptionButton):
  LEFT_MARGIN = 20

  def __init__(self, network: Network, wifi_state_callback: Callable[[], WifiState]):
    super().__init__(network.ssid)

    self.set_rect(rl.Rectangle(0, 0, gui_app.width, self.HEIGHT))

    self._selected_txt = gui_app.texture("icons_mici/settings/network/new/wifi_selected.png", 48, 96)

    self._network = network
    self._wifi_state_callback = wifi_state_callback
    self._wifi_icon = WifiIcon()
    self._wifi_icon.set_current_network(network)

  def set_network_missing(self, missing: bool):
    self._wifi_icon.set_network_missing(missing)

  def set_current_network(self, network: Network):
    self._network = network
    self._wifi_icon.set_current_network(network)

    # reset if we see the network again
    self.set_enabled(True)
    self.set_network_missing(False)

  def _render(self, _):
    disabled_alpha = 0.35 if not self.enabled else 1.0

    # connecting or connected
    if self._wifi_state_callback().ssid == self._network.ssid:
      selected_x = int(self._rect.x - self._selected_txt.width / 2)
      selected_y = int(self._rect.y + (self._rect.height - self._selected_txt.height) / 2)
      rl.draw_texture(self._selected_txt, selected_x, selected_y, rl.WHITE)

    self._wifi_icon.set_opacity(disabled_alpha)
    self._wifi_icon.set_scale((1.0 if self._selected else 0.65) * 0.7)
    self._wifi_icon.render(rl.Rectangle(
      self._rect.x + self.LEFT_MARGIN,
      self._rect.y,
      self.SELECTED_HEIGHT,
      self._rect.height
    ))

    if self._selected:
      self._label.set_font_size(self.SELECTED_HEIGHT)
      self._label.set_color(rl.Color(255, 255, 255, int(255 * 0.9 * disabled_alpha)))
      self._label.set_font_weight(FontWeight.DISPLAY)
    else:
      self._label.set_font_size(self.HEIGHT)
      self._label.set_color(rl.Color(255, 255, 255, int(255 * 0.58 * disabled_alpha)))
      self._label.set_font_weight(FontWeight.DISPLAY_REGULAR)

    label_offset = self.LEFT_MARGIN + self._wifi_icon.rect.width + 20
    label_rect = rl.Rectangle(self._rect.x + label_offset, self._rect.y, self._rect.width - label_offset, self._rect.height)
    self._label.set_text(normalize_ssid(self._network.ssid))
    self._label.render(label_rect)


class ConnectButton(Widget):
  CONNECT_FX_DURATION = 0.9

  def __init__(self):
    super().__init__()
    self._bg_txt = gui_app.texture("icons_mici/settings/network/new/connect_button.png", 410, 100)
    self._bg_pressed_txt = gui_app.texture("icons_mici/settings/network/new/connect_button_pressed.png", 410, 100)
    self._bg_full_txt = gui_app.texture("icons_mici/settings/network/new/full_connect_button.png", 520, 100)
    self._bg_full_pressed_txt = gui_app.texture("icons_mici/settings/network/new/full_connect_button_pressed.png", 520, 100)

    self._full: bool = False
    self._state: str = "connect"  # connect | connecting | connected
    self._state_t: float = rl.get_time()

    self._label = UnifiedLabel("", 36, FontWeight.MEDIUM, rl.Color(255, 255, 255, int(255 * 0.9)),
                               alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER,
                               alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE)

  @property
  def full(self) -> bool:
    return self._full

  def set_full(self, full: bool):
    self._full = full
    self.set_rect(rl.Rectangle(0, 0, 520 if self._full else 410, 100))

  def set_label(self, text: str):
    self._label.set_text(text)

  def set_state(self, state: str):
    if state != self._state:
      self._state = state
      self._state_t = rl.get_time()

  def _render(self, _):
    t = rl.get_time()
    if self._full:
      bg_txt = self._bg_full_pressed_txt if self.is_pressed and self.enabled else self._bg_full_txt
    else:
      bg_txt = self._bg_pressed_txt if self.is_pressed and self.enabled else self._bg_txt

    rl.draw_texture(bg_txt, int(self._rect.x), int(self._rect.y), rl.WHITE)

    cx = self._rect.x + self._rect.width / 2
    cy = self._rect.y + self._rect.height / 2
    dt = t - self._state_t

    if self._state == "connect":
      # subtle arming shine
      sheen = 0.5 + 0.5 * math.sin(t * 6.2)
      alpha = int(255 * (0.08 + 0.06 * sheen))
      rl.draw_rectangle_gradient_h(int(self._rect.x), int(self._rect.y + 8), int(self._rect.width), int(self._rect.height - 16),
                                   rl.Color(255, 255, 255, 0), rl.Color(255, 255, 255, alpha))
    elif self._state == "connecting":
      # active pulse + orbiting dots
      pulse = 0.5 + 0.5 * math.sin(t * 10.0)
      ring_alpha = int(255 * (0.14 + 0.20 * pulse))
      ring_r = 28 + 22 * pulse
      rl.draw_circle_lines(int(cx), int(cy), ring_r, rl.Color(166, 222, 255, ring_alpha))
      for i in range(3):
        phase = t * 7.0 + i * (2 * math.pi / 3)
        px = cx + math.cos(phase) * 26
        py = cy + math.sin(phase) * 8
        rl.draw_circle(int(px), int(py), 3, rl.Color(192, 234, 255, 210))
    else:  # connected
      # celebratory settle pulse on transition
      if dt < self.CONNECT_FX_DURATION:
        p = dt / self.CONNECT_FX_DURATION
        a = int(255 * (1 - p) ** 1.5 * 0.45)
        r = 24 + 52 * p
        rl.draw_circle_gradient(int(cx), int(cy), r, rl.Color(160, 240, 190, a), rl.Color(160, 240, 190, 0))

    self._label.set_text_color(rl.Color(255, 255, 255, int(255 * 0.9) if self.enabled else int(255 * 0.9 * 0.65)))
    self._label.render(self._rect)


class ForgetButton(Widget):
  HORIZONTAL_MARGIN = 8
  FORGET_FX_DURATION = 0.8

  def __init__(self, forget_network: Callable, open_network_manage_page):
    super().__init__()
    self._forget_network = forget_network
    self._open_network_manage_page = open_network_manage_page

    self._bg_txt = gui_app.texture("icons_mici/settings/network/new/forget_button.png", 100, 100)
    self._bg_pressed_txt = gui_app.texture("icons_mici/settings/network/new/forget_button_pressed.png", 100, 100)
    self._trash_txt = gui_app.texture("icons_mici/settings/network/new/trash.png", 35, 42)
    self.set_rect(rl.Rectangle(0, 0, 100 + self.HORIZONTAL_MARGIN * 2, 100))
    self._forget_fx_t: float | None = None

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)
    self._forget_fx_t = rl.get_time()
    dlg = BigConfirmationDialogV2("slide to forget", "icons_mici/settings/network/new/trash.png", red=True,
                                  confirm_callback=self._forget_network)
    gui_app.set_modal_overlay(dlg, callback=self._open_network_manage_page)

  def _render(self, _):
    t = rl.get_time()
    bg_txt = self._bg_pressed_txt if self.is_pressed else self._bg_txt
    wobble_x = math.sin(t * 15.0) * (1.5 if self.is_pressed else 0.0)
    draw_x = self._rect.x + self.HORIZONTAL_MARGIN + wobble_x
    rl.draw_texture(bg_txt, int(draw_x), int(self._rect.y), rl.WHITE)

    trash_x = int(self._rect.x + (self._rect.width - self._trash_txt.width) // 2 + wobble_x)
    trash_y = int(self._rect.y + (self._rect.height - self._trash_txt.height) // 2)
    rl.draw_texture(self._trash_txt, trash_x, trash_y, rl.WHITE)

    # danger pulse while hovering/pressing
    if self.is_pressed:
      pulse = 0.5 + 0.5 * math.sin(t * 12.0)
      a = int(255 * (0.12 + 0.22 * pulse))
      rl.draw_circle_gradient(int(self._rect.x + self._rect.width / 2), int(self._rect.y + self._rect.height / 2),
                              40 + 14 * pulse, rl.Color(255, 92, 92, a), rl.Color(255, 92, 92, 0))

    if self._forget_fx_t is not None:
      dt = t - self._forget_fx_t
      if dt < self.FORGET_FX_DURATION:
        p = dt / self.FORGET_FX_DURATION
        cx = self._rect.x + self._rect.width / 2
        cy = self._rect.y + self._rect.height / 2
        for i in range(16):
          ang = (i / 16) * (2 * math.pi) + i * 0.2
          rr = 10 + 48 * p
          px = cx + math.cos(ang) * rr
          py = cy + math.sin(ang) * rr
          alpha = int(255 * (1 - p) ** 1.55 * 0.7)
          rl.draw_circle(int(px), int(py), max(1, int(3 - 2 * p)), rl.Color(255, 120, 120, alpha))
      else:
        self._forget_fx_t = None


class NetworkInfoPage(NavWidget):
  CONNECT_BURST_DURATION = 0.85
  CONNECT_BURST_PARTICLES = 44
  AMBIENT_EVENT_MIN_INTERVAL = 3.5
  AMBIENT_EVENT_MAX_INTERVAL = 7.5
  AMBIENT_EVENT_DURATION = 1.2

  def __init__(self, wifi_manager, connect_callback: Callable, forget_callback: Callable, open_network_manage_page: Callable,
               connecting_callback: Callable[[], str | None], connected_callback: Callable[[], str | None]):
    super().__init__()
    self._wifi_manager = wifi_manager

    self.set_rect(rl.Rectangle(0, 0, gui_app.width, gui_app.height))

    self._wifi_icon = WifiIcon()
    self._forget_btn = ForgetButton(lambda: forget_callback(self._network.ssid) if self._network is not None else None,
                                    open_network_manage_page)
    self._connect_btn = ConnectButton()
    self._connect_btn.set_click_callback(lambda: connect_callback(self._network.ssid) if self._network is not None else None)

    self._title = UnifiedLabel("", 64, FontWeight.DISPLAY, rl.Color(255, 255, 255, int(255 * 0.9)),
                               alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE, scroll=True)
    self._subtitle = UnifiedLabel("", 36, FontWeight.ROMAN, rl.Color(255, 255, 255, int(255 * 0.9 * 0.65)),
                                  alignment_vertical=rl.GuiTextAlignmentVertical.TEXT_ALIGN_MIDDLE)

    self.set_back_callback(lambda: gui_app.set_modal_overlay(None))

    # State
    self._network: Network | None = None
    self._connecting_callback = connecting_callback
    self._connected_callback = connected_callback
    self._energy_filter = FirstOrderFilter(0.0, 0.08, 1 / gui_app.target_fps)
    self._connect_burst_t: float | None = None
    self._connect_btn_rect = rl.Rectangle(0, 0, 0, 0)
    self._forget_btn_rect = rl.Rectangle(0, 0, 0, 0)
    self._was_connected = False
    self._ambient_particles: list[dict[str, float]] = []
    self._ambient_event_t: float | None = None
    self._ambient_event_kind: str = ""
    self._next_ambient_event_t = rl.get_time() + random.uniform(self.AMBIENT_EVENT_MIN_INTERVAL, self.AMBIENT_EVENT_MAX_INTERVAL)

  def show_event(self):
    super().show_event()
    self._title.reset_scroll()

  def update_networks(self, networks: dict[str, Network]):
    # update current network from latest scan results
    for ssid, network in networks.items():
      if self._network is not None and ssid == self._network.ssid:
        self.set_current_network(network)
        break
    else:
      # network disappeared, close page
      gui_app.set_modal_overlay(None)

  def _update_state(self):
    super()._update_state()
    # Modal overlays stop main UI rendering, so we need to call here
    self._wifi_manager.process_callbacks()

    if self._network is None:
      return

    self._connect_btn.set_full(not self._wifi_manager.is_connection_saved(self._network.ssid) and not self._is_connecting)
    if self._is_connecting:
      self._connect_btn.set_label("connecting...")
      self._connect_btn.set_state("connecting")
      self._connect_btn.set_enabled(False)
    elif self._is_connected:
      self._connect_btn.set_label("connected")
      self._connect_btn.set_state("connected")
      self._connect_btn.set_enabled(False)
    elif self._network.security_type == SecurityType.UNSUPPORTED:
      self._connect_btn.set_label("connect")
      self._connect_btn.set_state("connect")
      self._connect_btn.set_enabled(False)
    else:  # saved or unknown
      self._connect_btn.set_label("connect")
      self._connect_btn.set_state("connect")
      self._connect_btn.set_enabled(True)

    self._title.set_text(normalize_ssid(self._network.ssid))
    if self._network.security_type == SecurityType.OPEN:
      self._subtitle.set_text("open")
    elif self._network.security_type == SecurityType.UNSUPPORTED:
      self._subtitle.set_text("unsupported")
    else:
      self._subtitle.set_text("secured")

    target_energy = 0.12
    if self._is_connecting:
      target_energy = 0.92
    elif self._is_connected:
      target_energy = 0.45

    if self._connect_btn.is_pressed:
      target_energy = max(target_energy, 0.85)
    if self._forget_btn.is_pressed:
      target_energy = max(target_energy, 0.6)
    self._energy_filter.update(target_energy)

    is_connected = self._is_connected
    if is_connected and not self._was_connected:
      self._connect_burst_t = rl.get_time()
    self._was_connected = is_connected

    now = rl.get_time()
    if self._network is not None and now >= self._next_ambient_event_t:
      self._trigger_ambient_event(now)
      self._next_ambient_event_t = now + random.uniform(self.AMBIENT_EVENT_MIN_INTERVAL, self.AMBIENT_EVENT_MAX_INTERVAL)

  def _spawn_particles(self, cx: float, cy: float, count: int, base_speed: float, spread: float = math.pi * 2):
    for i in range(count):
      angle = (i / max(1, count)) * spread + random.uniform(-0.25, 0.25)
      speed = base_speed * random.uniform(0.55, 1.45)
      self._ambient_particles.append({
        "x": cx,
        "y": cy,
        "vx": math.cos(angle) * speed,
        "vy": math.sin(angle) * speed,
        "t0": rl.get_time(),
      })

  def _trigger_ambient_event(self, now: float):
    kinds = ["signal_flare", "orbital_shimmer", "link_pulse"]
    self._ambient_event_kind = random.choice(kinds)
    self._ambient_event_t = now
    self._ambient_particles.clear()

    icon_cx = self._rect.x + 32 + self._wifi_icon.rect.width / 2
    icon_cy = self._rect.y + (self._rect.height - self._connect_btn.rect.height - self._wifi_icon.rect.height) / 2 + self._wifi_icon.rect.height / 2
    btn_cx = self._connect_btn_rect.x + self._connect_btn_rect.width / 2
    btn_cy = self._connect_btn_rect.y + self._connect_btn_rect.height / 2

    if self._ambient_event_kind == "signal_flare":
      self._spawn_particles(icon_cx, icon_cy, 26, 120.0)
    elif self._ambient_event_kind == "orbital_shimmer":
      self._spawn_particles(icon_cx, icon_cy, 20, 80.0, spread=math.pi * 1.3)
    else:
      self._spawn_particles(btn_cx, btn_cy, 24, 130.0)

  def set_current_network(self, network: Network):
    self._network = network
    self._wifi_icon.set_current_network(network)

  @property
  def _is_connecting(self):
    if self._network is None:
      return False
    is_connecting = self._connecting_callback() == self._network.ssid
    return is_connecting

  @property
  def _is_connected(self):
    if self._network is None:
      return False
    is_connected = self._connected_callback() == self._network.ssid
    return is_connected

  def _render(self, _):
    t = rl.get_time()
    energy = self._energy_filter.x

    # Ambient panel life in the popup.
    rl.draw_rectangle_gradient_v(int(self._rect.x), int(self._rect.y), int(self._rect.width), int(self._rect.height),
                                 rl.Color(98, 166, 255, int(255 * (0.04 + 0.09 * energy))),
                                 rl.Color(0, 0, 0, 0))

    self._wifi_icon.render(rl.Rectangle(
      self._rect.x + 32,
      self._rect.y + (self._rect.height - self._connect_btn.rect.height - self._wifi_icon.rect.height) / 2,
      self._wifi_icon.rect.width,
      self._wifi_icon.rect.height,
    ))

    self._title.render(rl.Rectangle(
      self._rect.x + self._wifi_icon.rect.width + 32 + 32,
      self._rect.y + 32 - 16,
      self._rect.width - (self._wifi_icon.rect.width + 32 + 32),
      64,
    ))

    self._subtitle.render(rl.Rectangle(
      self._rect.x + self._wifi_icon.rect.width + 32 + 32,
      self._rect.y + 32 + 64 - 16,
      self._rect.width - (self._wifi_icon.rect.width + 32 + 32),
      48,
    ))

    gyrate_mag = 3.0 + 4.0 * energy
    connect_x = self._rect.x + 8 + math.sin(t * (5.0 + 2.4 * energy)) * gyrate_mag
    connect_y = self._rect.y + self._rect.height - self._connect_btn.rect.height + math.sin(t * (8.5 + 1.8 * energy) + 1.1) * (1.4 + 2.0 * energy)
    self._connect_btn_rect = rl.Rectangle(connect_x, connect_y, self._connect_btn.rect.width, self._connect_btn.rect.height)

    self._connect_btn.render(self._connect_btn_rect)

    if not self._connect_btn.full:
      forget_x = self._rect.x + self._rect.width - self._forget_btn.rect.width + math.sin(t * (6.3 + 1.2 * energy) + 2.2) * (1.6 + 2.2 * energy)
      forget_y = self._rect.y + self._rect.height - self._forget_btn.rect.height + math.sin(t * (9.1 + 2.0 * energy) + 0.5) * (1.2 + 1.6 * energy)
      self._forget_btn_rect = rl.Rectangle(forget_x, forget_y, self._forget_btn.rect.width, self._forget_btn.rect.height)
      self._forget_btn.render(self._forget_btn_rect)

    # Connection success burst.
    if self._connect_burst_t is not None:
      dt = t - self._connect_burst_t
      if dt < self.CONNECT_BURST_DURATION:
        p = dt / self.CONNECT_BURST_DURATION
        cx = self._connect_btn_rect.x + self._connect_btn_rect.width / 2
        cy = self._connect_btn_rect.y + self._connect_btn_rect.height / 2
        for i in range(self.CONNECT_BURST_PARTICLES):
          angle = (i / self.CONNECT_BURST_PARTICLES) * (2 * math.pi) + math.sin(i * 1.31) * 0.22
          speed = 70 + (i % 9) * 15
          radius = speed * p
          px = cx + math.cos(angle) * radius
          py = cy + math.sin(angle) * radius - 16 * p
          alpha = int(255 * (1 - p) ** 1.65)
          size = max(1, int(2 + 4 * (1 - p)))
          color = rl.Color(160, 226, 255, alpha) if i % 2 == 0 else rl.Color(192, 142, 255, alpha)
          rl.draw_circle(int(px), int(py), size, color)
      else:
        self._connect_burst_t = None

    # Random ambient "single-player" moments.
    if self._ambient_event_t is not None:
      dt = t - self._ambient_event_t
      if dt < self.AMBIENT_EVENT_DURATION:
        phase = dt / self.AMBIENT_EVENT_DURATION

        if self._ambient_event_kind == "link_pulse":
          cx = self._connect_btn_rect.x + self._connect_btn_rect.width / 2
          cy = self._connect_btn_rect.y + self._connect_btn_rect.height / 2
          r = 30 + 140 * phase
          a = int(255 * (1.0 - phase) * 0.45)
          rl.draw_circle_lines(int(cx), int(cy), r, rl.Color(174, 224, 255, a))
        elif self._ambient_event_kind == "orbital_shimmer":
          cx = self._rect.x + 32 + self._wifi_icon.rect.width / 2
          cy = self._rect.y + (self._rect.height - self._connect_btn.rect.height - self._wifi_icon.rect.height) / 2 + self._wifi_icon.rect.height / 2
          for i in range(3):
            rr = 22 + 22 * i + 34 * phase
            aa = int(255 * (1.0 - phase) * (0.18 - i * 0.03))
            rl.draw_circle_lines(int(cx), int(cy), rr, rl.Color(188, 154, 255, max(0, aa)))

        alive_particles: list[dict[str, float]] = []
        for p in self._ambient_particles:
          pd = t - p["t0"]
          if pd > self.AMBIENT_EVENT_DURATION:
            continue
          pf = pd / self.AMBIENT_EVENT_DURATION
          x = p["x"] + p["vx"] * pf
          y = p["y"] + p["vy"] * pf - 22 * pf * (1.0 - pf)
          alpha = int(255 * (1.0 - pf) ** 1.5 * 0.6)
          radius = max(1, int(2 + 2 * (1.0 - pf)))
          color = rl.Color(160, 226, 255, alpha) if int(p["vx"]) % 2 == 0 else rl.Color(198, 152, 255, alpha)
          rl.draw_circle(int(x), int(y), radius, color)
          alive_particles.append(p)
        self._ambient_particles = alive_particles
      else:
        self._ambient_event_t = None
        self._ambient_event_kind = ""
        self._ambient_particles.clear()

    return -1


class WifiUIMici(BigMultiOptionDialog):
  def __init__(self, wifi_manager: WifiManager, back_callback: Callable):
    super().__init__([], None)

    # Set up back navigation
    self.set_back_callback(back_callback)

    self._network_info_page = NetworkInfoPage(wifi_manager, self._connect_to_network, wifi_manager.forget_connection, self._open_network_manage_page,
                                              lambda: wifi_manager.connecting_to_ssid, lambda: wifi_manager.connected_ssid)

    self._loading_animation = LoadingAnimation()

    self._wifi_manager = wifi_manager
    self._networks: dict[str, Network] = {}

    self._wifi_manager.add_callbacks(
      need_auth=self._on_need_auth,
      networks_updated=self._on_network_updated,
    )

  def show_event(self):
    # Clear scroller items and update from latest scan results
    super().show_event()
    self._wifi_manager.set_active(True)
    self._scroller._items.clear()
    self._update_buttons()

  def hide_event(self):
    super().hide_event()
    self._scroller.hide_event()

  def _open_network_manage_page(self, result=None):
    if self._network_info_page._network is not None and self._network_info_page._network.ssid in self._networks:
      self._network_info_page.update_networks(self._networks)
      gui_app.set_modal_overlay(self._network_info_page)

  def _on_network_updated(self, networks: list[Network]):
    self._networks = {network.ssid: network for network in networks}
    self._update_buttons()
    self._network_info_page.update_networks(self._networks)

  def _update_buttons(self):
    # Only add new buttons to the end. Update existing buttons without re-sorting so user can freely scroll around

    for network in self._networks.values():
      network_button_idx = next((i for i, btn in enumerate(self._scroller._items) if btn.option == network.ssid), None)
      if network_button_idx is not None:
        # Update network on existing button
        self._scroller._items[network_button_idx].set_current_network(network)
      else:
        network_button = WifiItem(network, lambda: self._wifi_manager.wifi_state)
        self._scroller.add_widget(network_button)

    # Move connecting/connected network to the start
    connected_btn_idx = next((i for i, btn in enumerate(self._scroller._items) if self._wifi_manager.wifi_state.ssid == btn._network.ssid), None)
    if connected_btn_idx is not None and connected_btn_idx > 0:
      self._scroller._items.insert(0, self._scroller._items.pop(connected_btn_idx))
      self._scroller._layout()  # fixes selected style single frame stutter

    # Disable networks no longer present
    for btn in self._scroller._items:
      if btn.option not in self._networks:
        btn.set_enabled(False)
        btn.set_network_missing(True)

  def _connect_with_password(self, ssid: str, password: str):
    self._wifi_manager.connect_to_network(ssid, password)
    self._update_buttons()

  def _on_option_selected(self, option: str):
    super()._on_option_selected(option)

    if option in self._networks:
      self._network_info_page.set_current_network(self._networks[option])
      self._open_network_manage_page()

  def _connect_to_network(self, ssid: str):
    network = self._networks.get(ssid)
    if network is None:
      cloudlog.warning(f"Trying to connect to unknown network: {ssid}")
      return

    if self._wifi_manager.is_connection_saved(network.ssid):
      self._wifi_manager.activate_connection(network.ssid)
      self._update_buttons()
    elif network.security_type == SecurityType.OPEN:
      self._wifi_manager.connect_to_network(network.ssid, "")
      self._update_buttons()
    else:
      self._on_need_auth(network.ssid, False)

  def _on_need_auth(self, ssid, incorrect_password=True):
    hint = "wrong password..." if incorrect_password else "enter password..."
    dlg = BigInputDialog(hint, "", minimum_length=8,
                         confirm_callback=lambda _password: self._connect_with_password(ssid, _password))

    def on_close(result=None):
      gui_app.set_modal_overlay_tick(None)
      self._open_network_manage_page(result)

    # Process wifi callbacks while the keyboard is shown so forgotten clears connecting state
    gui_app.set_modal_overlay_tick(self._wifi_manager.process_callbacks)
    gui_app.set_modal_overlay(dlg, on_close)

  def _render(self, _):
    super()._render(_)

    if not self._networks:
      self._loading_animation.render(self._rect)
