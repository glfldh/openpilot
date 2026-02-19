import time
import math

from cereal import log
import pyray as rl
from collections.abc import Callable
from openpilot.system.ui.widgets.label import gui_label, MiciLabel, UnifiedLabel
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, DEFAULT_TEXT_COLOR, MousePos
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.text import wrap_text
from openpilot.system.version import training_version, RELEASE_BRANCHES
from openpilot.common.filter_simple import FirstOrderFilter

HEAD_BUTTON_FONT_SIZE = 40
HOME_PADDING = 8

NetworkType = log.DeviceState.NetworkType

NETWORK_TYPES = {
  NetworkType.none: "Offline",
  NetworkType.wifi: "WiFi",
  NetworkType.cell2G: "2G",
  NetworkType.cell3G: "3G",
  NetworkType.cell4G: "LTE",
  NetworkType.cell5G: "5G",
  NetworkType.ethernet: "Ethernet",
}


class DeviceStatus(Widget):
  def __init__(self):
    super().__init__()
    self.set_rect(rl.Rectangle(0, 0, 300, 175))
    self._update_state()
    self._version_text = self._get_version_text()

    self._do_welcome()

  def _do_welcome(self):
    ui_state.params.put("CompletedTrainingVersion", training_version)

  def refresh(self):
    self._update_state()
    self._version_text = self._get_version_text()

  def _get_version_text(self) -> str:
    brand = "openpilot"
    description = ui_state.params.get("UpdaterCurrentDescription")
    return f"{brand} {description}" if description else brand

  def _update_state(self):
    # TODO: refresh function that can be called periodically, not at 60 fps, so we can update version
    # update system status
    self._system_status = "SYSTEM READY ✓" if ui_state.panda_type != log.PandaState.PandaType.unknown else "BOOTING UP..."

    # update network status
    strength = ui_state.sm['deviceState'].networkStrength.raw
    strength_text = "● " * strength + "○ " * (4 - strength)  # ◌ also works
    network_type = NETWORK_TYPES[ui_state.sm['deviceState'].networkType.raw]
    self._network_status = f"{network_type} {strength_text}"

  def _render(self, _):
    # draw status
    status_rect = rl.Rectangle(self._rect.x, self._rect.y, self._rect.width, 40)
    gui_label(status_rect, self._system_status, font_size=HEAD_BUTTON_FONT_SIZE, color=DEFAULT_TEXT_COLOR,
              font_weight=FontWeight.BOLD, alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER)

    # draw network status
    network_rect = rl.Rectangle(self._rect.x, self._rect.y + 60, self._rect.width, 40)
    gui_label(network_rect, self._network_status, font_size=40, color=DEFAULT_TEXT_COLOR,
              font_weight=FontWeight.MEDIUM, alignment=rl.GuiTextAlignment.TEXT_ALIGN_CENTER)

    # draw version
    version_font_size = 30
    version_rect = rl.Rectangle(self._rect.x, self._rect.y + 140, self._rect.width + 20, 40)
    wrapped_text = '\n'.join(wrap_text(self._version_text, version_font_size, version_rect.width))
    gui_label(version_rect, wrapped_text, font_size=version_font_size, color=DEFAULT_TEXT_COLOR,
              font_weight=FontWeight.MEDIUM, alignment=rl.GuiTextAlignment.TEXT_ALIGN_LEFT)


class MiciHomeLayout(Widget):
  def __init__(self):
    super().__init__()
    self._on_settings_click: Callable | None = None

    self._last_refresh = 0
    self._mouse_down_t: None | float = None
    self._did_long_press = False
    self._is_pressed_prev = False

    self._version_text = None
    self._experimental_mode = False
    self._alive_energy_filter = FirstOrderFilter(0.12, 0.08, 1 / gui_app.target_fps)

    self._settings_txt = gui_app.texture("icons_mici/settings.png", 48, 48)
    self._experimental_txt = gui_app.texture("icons_mici/experimental_mode.png", 48, 48)
    self._mic_txt = gui_app.texture("icons_mici/microphone.png", 32, 46)

    self._net_type = NETWORK_TYPES.get(NetworkType.none)
    self._net_strength = 0

    self._wifi_slash_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_slash.png", 50, 44)
    self._wifi_none_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_none.png", 50, 37)
    self._wifi_low_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_low.png", 50, 37)
    self._wifi_medium_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_medium.png", 50, 37)
    self._wifi_full_txt = gui_app.texture("icons_mici/settings/network/wifi_strength_full.png", 50, 37)

    self._cell_none_txt = gui_app.texture("icons_mici/settings/network/cell_strength_none.png", 54, 36)
    self._cell_low_txt = gui_app.texture("icons_mici/settings/network/cell_strength_low.png", 54, 36)
    self._cell_medium_txt = gui_app.texture("icons_mici/settings/network/cell_strength_medium.png", 54, 36)
    self._cell_high_txt = gui_app.texture("icons_mici/settings/network/cell_strength_high.png", 54, 36)
    self._cell_full_txt = gui_app.texture("icons_mici/settings/network/cell_strength_full.png", 54, 36)

    self._openpilot_label = MiciLabel("openpilot", font_size=96, color=rl.Color(255, 255, 255, int(255 * 0.9)), font_weight=FontWeight.DISPLAY)
    self._version_label = MiciLabel("", font_size=36, font_weight=FontWeight.ROMAN)
    self._large_version_label = MiciLabel("", font_size=64, color=rl.GRAY, font_weight=FontWeight.ROMAN)
    self._date_label = MiciLabel("", font_size=36, color=rl.GRAY, font_weight=FontWeight.ROMAN)
    self._branch_label = UnifiedLabel("", font_size=36, text_color=rl.GRAY, font_weight=FontWeight.ROMAN, scroll=True)
    self._version_commit_label = MiciLabel("", font_size=36, color=rl.GRAY, font_weight=FontWeight.ROMAN)

  def show_event(self):
    self._version_text = self._get_version_text()
    self._update_network_status(ui_state.sm['deviceState'])
    self._update_params()

  def _update_params(self):
    self._experimental_mode = ui_state.params.get_bool("ExperimentalMode")

  def _update_state(self):
    if self.is_pressed and not self._is_pressed_prev:
      self._mouse_down_t = time.monotonic()
    elif not self.is_pressed and self._is_pressed_prev:
      self._mouse_down_t = None
      self._did_long_press = False
    self._is_pressed_prev = self.is_pressed

    if self._mouse_down_t is not None:
      if time.monotonic() - self._mouse_down_t > 0.5:
        # long gating for experimental mode - only allow toggle if longitudinal control is available
        if ui_state.has_longitudinal_control:
          self._experimental_mode = not self._experimental_mode
          ui_state.params.put("ExperimentalMode", self._experimental_mode)
        self._mouse_down_t = None
        self._did_long_press = True

    if rl.get_time() - self._last_refresh > 5.0:
      device_state = ui_state.sm['deviceState']
      self._update_network_status(device_state)

      # Update version text
      self._version_text = self._get_version_text()
      self._last_refresh = rl.get_time()
      self._update_params()

    # Alive energy follows interaction and current device state.
    target_energy = 0.12
    if self.is_pressed:
      target_energy = 0.9
    elif ui_state.started:
      target_energy = 0.45
    elif self._net_type in (NetworkType.wifi, NetworkType.cell2G, NetworkType.cell3G, NetworkType.cell4G, NetworkType.cell5G):
      target_energy = 0.28
    self._alive_energy_filter.update(target_energy)

  def _update_network_status(self, device_state):
    self._net_type = device_state.networkType
    strength = device_state.networkStrength
    self._net_strength = max(0, min(5, strength.raw + 1)) if strength.raw > 0 else 0

  def set_callbacks(self, on_settings: Callable | None = None):
    self._on_settings_click = on_settings

  def _handle_mouse_release(self, mouse_pos: MousePos):
    if not self._did_long_press:
      if self._on_settings_click:
        self._on_settings_click()
    self._did_long_press = False

  def _get_version_text(self) -> tuple[str, str, str, str] | None:
    description = ui_state.params.get("UpdaterCurrentDescription")

    if description is not None and len(description) > 0:
      # Expect "version / branch / commit / date"; be tolerant of other formats
      try:
        version, branch, commit, date = description.split(" / ")
        return version, branch, commit, date
      except Exception:
        return None

    return None

  def _render(self, _):
    t = rl.get_time()
    alive = self._alive_energy_filter.x

    # Home hero ambiance (subtle, cinematic).
    rl.draw_rectangle_gradient_v(int(self._rect.x), int(self._rect.y), int(self._rect.width), int(self._rect.height),
                                 rl.Color(90, 154, 255, int(255 * (0.035 + 0.06 * alive))),
                                 rl.Color(8, 12, 24, 0))
    # Slow drifting color blobs.
    blob_a = int(255 * (0.028 + 0.05 * alive))
    bx1 = self._rect.x + self._rect.width * (0.24 + 0.10 * math.sin(t * 0.23))
    by1 = self._rect.y + self._rect.height * (0.30 + 0.10 * math.cos(t * 0.19))
    bx2 = self._rect.x + self._rect.width * (0.76 + 0.08 * math.cos(t * 0.21 + 0.8))
    by2 = self._rect.y + self._rect.height * (0.66 + 0.08 * math.sin(t * 0.24 + 1.5))
    r1 = max(60, int(min(self._rect.width, self._rect.height) * 0.14))
    r2 = max(70, int(min(self._rect.width, self._rect.height) * 0.17))
    rl.draw_circle_gradient(int(bx1), int(by1), float(r1), rl.Color(120, 190, 255, blob_a), rl.Color(120, 190, 255, 0))
    rl.draw_circle_gradient(int(bx2), int(by2), float(r2), rl.Color(176, 142, 255, blob_a), rl.Color(176, 142, 255, 0))
    # Thin atmosphere sweep keeps the full scene moving.
    sweep = 0.5 + 0.5 * math.sin(t * (0.9 + 0.7 * alive))
    sweep_x = int(self._rect.x + self._rect.width * (-0.22 + 1.42 * sweep))
    sweep_w = int(150 + 90 * alive)
    sweep_h = int(self._rect.height * 0.68)
    sweep_y = int(self._rect.y + self._rect.height * 0.08)
    sweep_alpha = int(255 * (0.025 + 0.045 * alive))
    rl.draw_rectangle_gradient_h(sweep_x - sweep_w, sweep_y, sweep_w * 2, sweep_h,
                                 rl.Color(160, 214, 255, 0), rl.Color(160, 214, 255, sweep_alpha))

    # TODO: why is there extra space here to get it to be flush?
    title_float = math.sin(t * (1.6 + 0.8 * alive)) * (1.8 + 1.9 * alive)
    text_pos = rl.Vector2(self.rect.x - 2 + HOME_PADDING, self.rect.y - 16 + title_float)
    # Halo behind home title.
    halo_pulse = 0.5 + 0.5 * math.sin(t * (2.6 + 2.0 * alive))
    halo_alpha = int(255 * (0.05 + 0.12 * alive) * (0.65 + 0.35 * halo_pulse))
    rl.draw_circle_gradient(int(text_pos.x + 140), int(text_pos.y + 60), 120 + 20 * halo_pulse,
                            rl.Color(165, 216, 255, halo_alpha), rl.Color(165, 216, 255, 0))
    self._openpilot_label.set_position(text_pos.x, text_pos.y)
    self._openpilot_label.render()

    if self._version_text is not None:
      # release branch
      release_branch = self._version_text[1] in RELEASE_BRANCHES
      version_float = math.sin(t * (1.2 + 0.5 * alive) + 0.9) * (1.2 + 1.6 * alive)
      version_pos = rl.Rectangle(text_pos.x, text_pos.y + self._openpilot_label.font_size + 16 + version_float, 100, 44)
      self._version_label.set_text(self._version_text[0])
      self._version_label.set_position(version_pos.x, version_pos.y)
      self._version_label.render()

      self._date_label.set_text(" " + self._version_text[3])
      self._date_label.set_position(version_pos.x + self._version_label.rect.width + 10, version_pos.y)
      self._date_label.render()

      self._branch_label.set_max_width(gui_app.width - self._version_label.rect.width - self._date_label.rect.width - 32)
      self._branch_label.set_text(" " + ("release" if release_branch else self._version_text[1]))
      self._branch_label.set_position(version_pos.x + self._version_label.rect.width + self._date_label.rect.width + 20, version_pos.y)
      self._branch_label.render()

      if not release_branch:
        # 2nd line
        self._version_commit_label.set_text(self._version_text[2])
        self._version_commit_label.set_position(version_pos.x, version_pos.y + self._date_label.font_size + 7)
        self._version_commit_label.render()

    self._render_bottom_status_bar()

  def _render_bottom_status_bar(self):
    # ***** Center-aligned bottom section icons *****

    # TODO: refactor repeated icon drawing into a small loop
    ITEM_SPACING = 18
    Y_CENTER = 24

    last_x = self.rect.x + HOME_PADDING

    # Draw settings icon in bottom left corner
    t = rl.get_time()
    alive = self._alive_energy_filter.x
    def draw_alive_icon(texture: rl.Texture, x: float, phase: float, glow_rgb: tuple[int, int, int], alpha: int = 230,
                        y_offset: float = 0.0) -> float:
      bob = math.sin(t * (2.2 + 1.2 * alive) + phase) * (1.2 + 2.1 * alive)
      pulse = 0.5 + 0.5 * math.sin(t * (3.4 + 1.6 * alive) + phase * 1.6)
      icon_y = self._rect.y + self.rect.height - texture.height / 2 - Y_CENTER + bob + y_offset
      glow_a = int(255 * (0.05 + 0.17 * alive) * (0.55 + 0.45 * pulse))
      glow_r = 26 + 10 * pulse + 8 * alive
      rl.draw_circle_gradient(int(x + texture.width / 2), int(icon_y + texture.height / 2), glow_r,
                              rl.Color(glow_rgb[0], glow_rgb[1], glow_rgb[2], glow_a),
                              rl.Color(glow_rgb[0], glow_rgb[1], glow_rgb[2], 0))
      # Tiny top sheen for "alive" feel.
      sheen_w = int(texture.width * 0.5)
      sheen_x = int(x + texture.width * (0.25 + 0.35 * pulse))
      sheen_y = int(icon_y + texture.height * 0.16)
      rl.draw_rectangle_gradient_h(sheen_x - sheen_w // 2, sheen_y, sheen_w, 2,
                                   rl.Color(255, 255, 255, 0),
                                   rl.Color(255, 255, 255, int(46 + 45 * alive)))
      rl.draw_texture(texture, int(x), int(icon_y), rl.Color(255, 255, 255, alpha))
      return x + texture.width + ITEM_SPACING

    last_x = draw_alive_icon(self._settings_txt, last_x, 0.2, (150, 210, 255), alpha=int(255 * 0.9))

    # draw network
    if self._net_type == NetworkType.wifi:
      # There is no 1
      draw_net_txt = {0: self._wifi_none_txt,
                      2: self._wifi_low_txt,
                      3: self._wifi_medium_txt,
                      4: self._wifi_full_txt,
                      5: self._wifi_full_txt}.get(self._net_strength, self._wifi_low_txt)
      last_x = draw_alive_icon(draw_net_txt, last_x, 1.0, (134, 220, 255), alpha=int(255 * 0.9))

    elif self._net_type in (NetworkType.cell2G, NetworkType.cell3G, NetworkType.cell4G, NetworkType.cell5G):
      draw_net_txt = {0: self._cell_none_txt,
                      2: self._cell_low_txt,
                      3: self._cell_medium_txt,
                      4: self._cell_high_txt,
                      5: self._cell_full_txt}.get(self._net_strength, self._cell_none_txt)
      last_x = draw_alive_icon(draw_net_txt, last_x, 1.45, (166, 196, 255), alpha=int(255 * 0.9))

    else:
      # No network
      # Offset by difference in height between slashless and slash icons to make center align match
      slash_y_offset = -(self._wifi_slash_txt.height - self._wifi_none_txt.height) / 2
      last_x = draw_alive_icon(self._wifi_slash_txt, last_x, 1.8, (194, 146, 255), alpha=int(255 * 0.9), y_offset=slash_y_offset)

    # draw experimental icon
    if self._experimental_mode:
      last_x = draw_alive_icon(self._experimental_txt, last_x, 2.3, (176, 146, 255), alpha=255)

    # draw microphone icon when recording audio is enabled
    if ui_state.recording_audio:
      last_x = draw_alive_icon(self._mic_txt, last_x, 2.8, (142, 236, 216), alpha=255)
