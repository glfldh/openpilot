import pyray as rl
rl.set_config_flags(rl.ConfigFlags.FLAG_WINDOW_HIDDEN)

import unittest
from hypothesis import given, settings, strategies as st

from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.wifi_manager import Network, SecurityType, WifiState, ConnectStatus, normalize_ssid
from openpilot.selfdrive.ui.mici.layouts.settings.network.wifi_ui import WifiButton
from openpilot.selfdrive.ui.mici.layouts.settings.network import WifiNetworkButton


class FakeWifiManager:
  def __init__(self):
    self.wifi_state = WifiState()
    self._networks: list[Network] = []
    self.ipv4_address: str = ""
    self._saved_ssids: set[str] = set()

  @property
  def networks(self) -> list[Network]:
    return self._networks

  @property
  def connecting_to_ssid(self) -> str | None:
    return self.wifi_state.ssid if self.wifi_state.status == ConnectStatus.CONNECTING else None

  @property
  def connected_ssid(self) -> str | None:
    return self.wifi_state.ssid if self.wifi_state.status == ConnectStatus.CONNECTED else None

  def is_connection_saved(self, ssid: str) -> bool:
    return ssid in self._saved_ssids

  def add_callbacks(self, **kwargs):
    pass

  def set_active(self, active: bool):
    pass

  def forget_connection(self, ssid: str):
    pass


# -- Hypothesis strategies --

SSID_ST = st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N')))

NETWORK_ST = st.builds(
  Network,
  ssid=SSID_ST,
  strength=st.integers(min_value=0, max_value=100),
  security_type=st.sampled_from(list(SecurityType)),
  is_tethering=st.booleans(),
)

IPV4_ST = st.text(max_size=40)


@st.composite
def WIFI_SCENARIOS(draw):
  networks = draw(st.lists(NETWORK_ST, min_size=0, max_size=8, unique_by=lambda n: n.ssid))
  ssids = [n.ssid for n in networks]
  status = draw(st.sampled_from(list(ConnectStatus)))
  ipv4 = draw(IPV4_ST)
  print(ipv4)

  if ssids:
    ssid = draw(st.one_of(st.sampled_from(ssids), SSID_ST, st.none()))
  else:
    ssid = draw(st.one_of(SSID_ST, st.none()))

  saved = draw(st.frozensets(st.sampled_from(ssids) if ssids else st.nothing(), max_size=len(ssids)))

  return networks, WifiState(ssid=ssid, status=status), ipv4, saved


class TestWifiUIInvariants(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    gui_app.init_window("test-wifi-invariants")
    cls.fake_wm = FakeWifiManager()
    cls.wifi_network_btn = WifiNetworkButton(cls.fake_wm)

  @classmethod
  def tearDownClass(cls):
    gui_app.close()

  @given(scenario=WIFI_SCENARIOS())
  @settings(max_examples=500, deadline=None)
  def test_connection_status_consistent(self, scenario):
    """WifiNetworkButton and the matching WifiButton must agree on connection state."""
    networks, wifi_state, ipv4, saved = scenario

    self.fake_wm.wifi_state = wifi_state
    self.fake_wm._networks = networks
    self.fake_wm.ipv4_address = ipv4
    self.fake_wm._saved_ssids = set(saved)

    self.wifi_network_btn._update_state()
    wifi_buttons = {n.ssid: WifiButton(n, self.fake_wm) for n in networks}
    for btn in wifi_buttons.values():
      btn._update_state()

    active_ssid = wifi_state.ssid
    connecting_btns = [b for b in wifi_buttons.values() if b._is_connecting]
    connected_btns = [b for b in wifi_buttons.values() if b._is_connected]

    # At most one button is connecting and at most one is connected
    assert len(connecting_btns) <= 1
    assert len(connected_btns) <= 1

    # A single button can't be both connecting and connected
    for btn in wifi_buttons.values():
      assert not (btn._is_connecting and btn._is_connected)

    # If a WifiButton thinks it's connecting/connected, WifiNetworkButton must show that ssid
    if connecting_btns:
      assert self.wifi_network_btn.text == normalize_ssid(connecting_btns[0].network.ssid)
    if connected_btns:
      assert self.wifi_network_btn.text == normalize_ssid(connected_btns[0].network.ssid)

    # Converse: if WifiNetworkButton shows a specific ssid and that ssid has a button,
    # that button must be the one connecting or connected
    if active_ssid and active_ssid in wifi_buttons:
      btn = wifi_buttons[active_ssid]
      if wifi_state.status == ConnectStatus.CONNECTING:
        assert btn._is_connecting
      elif wifi_state.status == ConnectStatus.CONNECTED:
        assert btn._is_connected

    # No non-active button should claim connecting or connected
    for ssid, btn in wifi_buttons.items():
      if ssid != active_ssid:
        assert not btn._is_connecting, f"'{ssid}' claims connecting but active is '{active_ssid}'"
        assert not btn._is_connected, f"'{ssid}' claims connected but active is '{active_ssid}'"

    # Connected/connecting buttons must be disabled
    for btn in connecting_btns + connected_btns:
      assert not btn.enabled


if __name__ == "__main__":
  unittest.main()
