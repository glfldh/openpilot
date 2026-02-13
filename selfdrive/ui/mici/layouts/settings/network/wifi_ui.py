import math
import numpy as np
import pyray as rl
from collections.abc import Callable

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.swaglog import cloudlog
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.selfdrive.ui.mici.widgets.dialog import BigInputDialog, BigConfirmationDialogV2
from openpilot.selfdrive.ui.mici.widgets.button import BigButton, LABEL_COLOR, LABEL_HORIZONTAL_PADDING, LABEL_VERTICAL_PADDING
from openpilot.system.ui.lib.application import gui_app, MousePos, FontWeight
from openpilot.system.ui.widgets import Widget, NavWidget
from openpilot.system.ui.widgets.scroller import Scroller
from openpilot.system.ui.lib.wifi_manager import WifiManager, Network, SecurityType


def normalize_ssid(ssid: str) -> str:
  return ssid.replace("’", "'")  # for iPhone hotspots


class LoadingAnimation(Widget):
  def __init__(self):
    super().__init__()
    self._opacity_target = 1.0
    self._opacity_filter = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)

  def set_opacity(self, opacity: float):
    self._opacity_target = opacity

  def _render(self, _):
    # rl.draw_rectangle_lines_ex(self._rect, 1, rl.RED)

    self._opacity_filter.update(self._opacity_target)

    if self._opacity_filter.x <= 0.01:
      return

    cx = int(self._rect.x + self._rect.width / 2)
    cy = int(self._rect.y + self._rect.height / 2)

    y_mag = 7
    anim_scale = 5
    spacing = 14

    for i in range(3):
      x = cx - spacing + i * spacing
      y = int(cy + min(math.sin((rl.get_time() - i * 0.2) * anim_scale) * y_mag, 0))
      alpha = int(np.interp(cy - y, [0, y_mag], [255 * 0.45, 255 * 0.9]) * self._opacity_filter.x)
      rl.draw_circle(x, y, 5, rl.Color(255, 255, 255, alpha))


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
    self._scale = 0.6  # TODO: remove this
    self._opacity = 1.0

  def set_current_network(self, network: Network):
    self._network = network

  def set_network_missing(self, missing: bool):
    self._network_missing = missing

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
    icon_x = self._rect.x + (self._rect.width - strength_icon.width * self._scale) // 2
    icon_y = self._rect.y + (self._rect.height - strength_icon.height * self._scale) // 2
    rl.draw_texture_ex(strength_icon, (icon_x, icon_y), 0.0, self._scale, tint)

    # Render lock icon at lower right of wifi icon if secured
    if self._network.security_type not in (SecurityType.OPEN, SecurityType.UNSUPPORTED):
      lock_scale = self._scale * 1.1
      lock_x = int(icon_x + 1 + strength_icon.width * self._scale - self._lock_txt.width * lock_scale / 2)
      lock_y = int(icon_y + 1 + strength_icon.height * self._scale - self._lock_txt.height * lock_scale / 2)
      rl.draw_texture_ex(self._lock_txt, (lock_x, lock_y), 0.0, lock_scale, tint)


class Divider(Widget):
  def __init__(self):
    super().__init__()
    self.set_rect(rl.Rectangle(0, 0, 4, 120))

  def _render(self, _):
    # rounded edges, 45% white
    rl.draw_rectangle_rounded(self._rect, self._rect.width / 2, 4, rl.Color(255, 255, 255, int(255 * 0.45)))


class WifiButton(BigButton):
  LABEL_PADDING = 98
  LABEL_WIDTH = 402 - 98 - 28  # button width - left padding - right padding

  def __init__(self, network: Network, forget_callback: Callable[[str], None]):
    super().__init__(normalize_ssid(network.ssid), scroll=True)

    # State
    self._network = network
    self._network_missing = False
    self._connecting: Callable[[], str | None] | None = None
    self._wifi_icon = WifiIcon()
    self._wifi_icon.set_current_network(network)
    self._forget_btn = ForgetButton(lambda: forget_callback(self._network.ssid))
    self._check_txt = gui_app.texture("icons_mici/setup/driver_monitoring/dm_check.png", 32, 32)
    self._animate_from_x: float | None = None
    self._position_filter = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)

  @property
  def network(self) -> Network:
    return self._network

  @property
  def is_pressed(self) -> bool:
    return super().is_pressed and not self._forget_btn.is_pressed

  def animate_from(self, old_x: float):
    print('animate_from', old_x)
    """Start animating from old_x to wherever the scroller places us next."""
    self._animate_from_x = old_x

  def set_position(self, x: float, y: float) -> None:
    if self._animate_from_x is not None:
      self._position_filter.x = self._animate_from_x - x
      self._animate_from_x = None
      # skip update this call so first frame starts exactly at old_x
    else:
      self._position_filter.update(0.0)

    super().set_position(x + self._position_filter.x, y)

  def _get_label_font_size(self):
    return 48

  def _draw_content(self, btn_y: float):
    self._label.set_color(LABEL_COLOR)
    label_rect = rl.Rectangle(self._rect.x + self.LABEL_PADDING, btn_y + LABEL_VERTICAL_PADDING,
                              self.LABEL_WIDTH, self._rect.height - LABEL_VERTICAL_PADDING * 2)
    self._label.render(label_rect)

    if self.value:
      sub_label_x = self._rect.x + LABEL_HORIZONTAL_PADDING
      label_y = btn_y + self._rect.height - LABEL_VERTICAL_PADDING
      sub_label_height = self._sub_label.get_content_height(self.LABEL_WIDTH)

      if self._network.is_connected and not self._is_connecting and not self._network_missing:
        check_y = int(label_y - sub_label_height + (sub_label_height - self._check_txt.height) / 2)
        rl.draw_texture(self._check_txt, int(sub_label_x), check_y, rl.Color(255, 255, 255, int(255 * 0.9 * 0.65)))
        sub_label_x += self._check_txt.width + 14

      sub_label_rect = rl.Rectangle(sub_label_x, label_y - sub_label_height, self.LABEL_WIDTH, sub_label_height)
      self._sub_label.render(sub_label_rect)

    # Wifi icon
    self._wifi_icon.set_opacity(0.35 if self._network_missing else 1.0)
    wifi_icon_rect = rl.Rectangle(
      self._rect.x,
      btn_y + 23,
      self._wifi_icon.rect.width,
      self._wifi_icon.rect.height,
    )
    self._wifi_icon.render(wifi_icon_rect)
    # rl.draw_rectangle_lines_ex(wifi_icon_rect, 1, rl.RED)

    # Forget button
    if (self._network.is_saved or self._is_connecting) and not self._network_missing:
      self._forget_btn.render(rl.Rectangle(
        self._rect.x + self._rect.width - self._forget_btn.rect.width,
        btn_y + self._rect.height - self._forget_btn.rect.height,
        self._forget_btn.rect.width,
        self._forget_btn.rect.height,
      ))

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(touch_callback)
    self._forget_btn.set_touch_valid_callback(touch_callback)

  def set_current_network(self, network: Network):
    self._network = network
    self._wifi_icon.set_current_network(network)
    self._network_missing = False
    self._wifi_icon.set_network_missing(False)

  def set_network_missing(self, missing: bool):
    self._network_missing = missing
    self._wifi_icon.set_network_missing(missing)

  def set_connecting(self, is_connecting: Callable[[], str | None]):
    self._connecting = is_connecting

  @property
  def _is_connecting(self):
    # TODO: make this passed in so it's never none
    if self._connecting is None:
      return False
    is_connecting = self._connecting() == self._network.ssid
    return is_connecting

  def _update_state(self):
    if self._network_missing or self._is_connecting or self._network.is_connected or self._network.security_type == SecurityType.UNSUPPORTED:
      self.set_enabled(False)
      self._sub_label.set_color(rl.Color(255, 255, 255, int(255 * 0.585)))
      self._sub_label.set_font_weight(FontWeight.ROMAN)

      if self._network_missing:
        self.set_value("not in range")
      elif self._is_connecting:
        self.set_value("connecting...")
      elif self._network.is_connected:
        self.set_value("connected")
      else:
        self.set_value("unsupported")

    else:  # saved or unknown
      self.set_value("connect")
      self.set_enabled(True)
      self._sub_label.set_color(rl.Color(255, 255, 255, int(255 * 0.9)))
      self._sub_label.set_font_weight(FontWeight.SEMI_BOLD)


class ForgetButton(Widget):
  MARGIN = 12  # bottom and right

  def __init__(self, forget_network: Callable):
    super().__init__()
    self._forget_network = forget_network

    self._bg_txt = gui_app.texture("icons_mici/settings/network/new/forget_button.png", 84, 84)
    self._bg_pressed_txt = gui_app.texture("icons_mici/settings/network/new/forget_button_pressed.png", 84, 84)
    self._trash_txt = gui_app.texture("icons_mici/settings/network/new/trash.png", 29, 35)
    self.set_rect(rl.Rectangle(0, 0, 84 + self.MARGIN * 2, 84 + self.MARGIN * 2))

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)
    dlg = BigConfirmationDialogV2("slide to forget", "icons_mici/settings/network/new/trash.png", red=True,
                                  confirm_callback=self._forget_network)
    gui_app.set_modal_overlay(dlg)

  def _render(self, _):
    bg_txt = self._bg_pressed_txt if self.is_pressed else self._bg_txt
    rl.draw_texture_ex(bg_txt, (self._rect.x + (self._rect.width - self._bg_txt.width) / 2,
                                self._rect.y + (self._rect.height - self._bg_txt.height) / 2), 0, 1.0, rl.WHITE)

    trash_x = self._rect.x + (self._rect.width - self._trash_txt.width) / 2
    trash_y = self._rect.y + (self._rect.height - self._trash_txt.height) / 2
    rl.draw_texture_ex(self._trash_txt, (trash_x, trash_y), 0, 1.0, rl.WHITE)


class WifiUIMici(NavWidget):
  def __init__(self, wifi_manager: WifiManager, back_callback: Callable):
    super().__init__()

    self._scroller = Scroller([],
                              # horizontal=False, pad_start=100, pad_end=100, spacing=0, snap_items=True
                              snap_items=False,
                              )
    self._saved_divider = Divider()

    # Set up back navigation
    self.set_back_callback(back_callback)

    self._loading_animation = LoadingAnimation()

    self._wifi_manager = wifi_manager
    self._connecting: str | None = None
    self._networks: dict[str, Network] = {}

    self._wifi_manager.add_callbacks(
      need_auth=self._on_need_auth,
      activated=self._on_activated,
      forgotten=self._on_forgotten,
      networks_updated=self._on_network_updated,
      disconnected=self._on_disconnected,
    )

  def show_event(self):
    # Call super to prepare scroller; selection scroll is handled dynamically
    super().show_event()
    self._scroller.show_event()
    self._wifi_manager.set_active(True)

    # # TEMP: fake networks for testing without dbus
    # fake_networks = [
    #   Network(ssid="HomeWifi", strength=90, is_connected=True, security_type=SecurityType.OPEN, is_saved=True),
    #   Network(ssid="OfficeNet", strength=75, is_connected=False, security_type=SecurityType.OPEN, is_saved=True),
    #   Network(ssid="CoffeeShop", strength=60, is_connected=False, security_type=SecurityType.OPEN, is_saved=False),
    #   Network(ssid="Neighbor5G", strength=45, is_connected=False, security_type=SecurityType.OPEN, is_saved=False),
    #   Network(ssid="GuestNetwork", strength=80, is_connected=False, security_type=SecurityType.OPEN, is_saved=False),
    #   Network(ssid="xfinitywifi", strength=30, is_connected=False, security_type=SecurityType.OPEN, is_saved=False),
    #   Network(ssid="MyHotspot", strength=55, is_connected=False, security_type=SecurityType.OPEN, is_saved=True),
    # ]
    # self._on_network_updated(fake_networks)

  def hide_event(self):
    super().hide_event()
    self._wifi_manager.set_active(False)
    # clear scroller items to remove old networks on next show
    self._scroller._items.clear()

  def _forget_network(self, ssid: str):
    network = self._networks.get(ssid)
    if network is None:
      cloudlog.warning(f"Trying to forget unknown network: {ssid}")
      return

    self._wifi_manager.forget_connection(network.ssid)

  def _on_network_updated(self, networks: list[Network]):
    self._networks = {network.ssid: network for network in networks}
    self._update_buttons()

  def _update_buttons(self):
    existing = {btn.network.ssid: btn for btn in self._scroller._items if isinstance(btn, WifiButton)}
    is_known = lambda n: n.is_connected or n.is_saved or n.ssid == self._connecting

    # Update existing buttons, add new ones in the correct section
    num_known_inserted = 0
    for network in self._networks.values():
      if network.ssid in existing:
        existing[network.ssid].set_current_network(network)
      else:
        btn = WifiButton(network, self._forget_network)
        btn.set_click_callback(lambda ssid=network.ssid: self._connect_to_network(ssid))
        btn.set_connecting(lambda: self._connecting)

        if is_known(network):
          # Insert before first unknown button so it appears in the saved section
          insert_idx = next((i for i, b in enumerate(self._scroller._items)
                             if isinstance(b, WifiButton) and not is_known(b.network)), len(self._scroller._items))
          self._scroller.add_widget(btn)
          self._scroller._items.pop()
          self._scroller._items.insert(insert_idx, btn)
          num_known_inserted += 1
        else:
          self._scroller.add_widget(btn)

    # Compensate scroll offset so visible items don't jump when buttons are inserted before them
    if num_known_inserted > 0:
      offset = num_known_inserted * (btn.rect.width + self._scroller._spacing)
      self._scroller.scroll_panel.set_offset(self._scroller.scroll_panel.get_offset() - offset)

    # Mark networks no longer in scan results (display handled by _update_state)
    for btn in self._scroller._items:
      if isinstance(btn, WifiButton) and btn.network.ssid not in self._networks:
        btn.set_network_missing(True)

    # Move connecting/connected network to the front with animation (prefer connecting over connected)
    front_btn_idx = next((i for i, btn in enumerate(self._scroller._items)
                          if isinstance(btn, WifiButton) and not btn._network_missing
                          and (btn.network.ssid == self._connecting or
                               (not self._connecting and btn.network.is_connected))), None)

    if front_btn_idx is not None and front_btn_idx > 0:
      btn = self._scroller._items[front_btn_idx]
      old_x = btn.rect.x
      self._scroller._items.insert(0, self._scroller._items.pop(front_btn_idx))
      btn.animate_from(old_x)

    # Insert divider between known (saved/connecting/connected) and unknown groups
    if self._saved_divider in self._scroller._items:
      self._scroller._items.remove(self._saved_divider)

    if any(is_known(n) for n in self._networks.values()) and any(not is_known(n) for n in self._networks.values()):
      divider_idx = next(i for i, btn in enumerate(self._scroller._items)
                         if isinstance(btn, WifiButton) and not is_known(btn.network))
      self._scroller._items.insert(divider_idx, self._saved_divider)

  def _connect_with_password(self, ssid: str, password: str):
    import os
    password = os.getenv('WIFI_PASSWORD', password)
    if password:
      self._connecting = ssid
      self._scroller.scroll_to(self._scroller.scroll_panel.get_offset(), smooth=True)
      self._wifi_manager.connect_to_network(ssid, password)
      self._update_buttons()

  def _connect_to_network(self, ssid: str):
    network = self._networks.get(ssid)
    if network is None:
      cloudlog.warning(f"Trying to connect to unknown network: {ssid}")
      return

    print('connecting to', ssid, 'saved:', network.is_saved, 'security:', network.security_type)
    if network.is_saved:
      self._connecting = network.ssid
      self._scroller.scroll_to(self._scroller.scroll_panel.get_offset(), smooth=True)
      self._wifi_manager.activate_connection(network.ssid)
      self._update_buttons()
    elif network.security_type == SecurityType.OPEN:
      self._connecting = network.ssid
      self._scroller.scroll_to(self._scroller.scroll_panel.get_offset(), smooth=True)
      self._wifi_manager.connect_to_network(network.ssid, "")
      self._update_buttons()
    else:
      self._on_need_auth(network.ssid, False)

  def _on_need_auth(self, ssid, incorrect_password=True):
    hint = "wrong password..." if incorrect_password else "enter password..."
    dlg = BigInputDialog(hint, "", minimum_length=0,
                         confirm_callback=lambda _password: self._connect_with_password(ssid, _password))
    gui_app.set_modal_overlay(dlg)

  def _on_activated(self):
    self._connecting = None

  def _on_forgotten(self):
    self._connecting = None

  def _on_disconnected(self):
    self._connecting = None

  # def _update_state(self):
  #   super()._update_state()
  #   if self.is_pressed:
  #     self._last_interaction_time = rl.get_time()
  #     self._loading_animation.set_opacity(0.0)
  #   elif rl.get_time() - self._last_interaction_time >= self.INACTIVITY_TIMEOUT:
  #     self._loading_animation.set_opacity(1.0)
  #
  #   if len(self._networks) == 0:
  #     self._loading_animation.set_opacity(1.0)

  def _render(self, _):
    self._scroller.render(self._rect)

    anim_x = self._rect.x
    anim_y = self._rect.y + self._rect.height - 25 + 2
    self._loading_animation.render(rl.Rectangle(anim_x, anim_y, 90, 20))
