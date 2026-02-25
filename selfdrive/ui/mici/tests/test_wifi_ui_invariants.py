import pyray as rl
rl.set_config_flags(rl.ConfigFlags.FLAG_WINDOW_HIDDEN)

import unittest
import hypothesis.strategies as st
from hypothesis import given, settings, Phase

from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.wifi_manager import Network, SecurityType, WifiState, ConnectStatus
from openpilot.selfdrive.ui.mici.layouts.settings.network.wifi_ui import WifiUIMici, WifiButton
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

  def connect_to_network(self, ssid: str, password: str):
    pass


def _get_buttons(wifi_ui: WifiUIMici) -> dict[str, WifiButton]:
  return {btn.network.ssid: btn for btn in wifi_ui._scroller.items if isinstance(btn, WifiButton)}


def _check_disabled_invariant(buttons: dict[str, WifiButton]):
  for btn in buttons.values():
    should_disable = (btn._is_connecting or btn._is_connected or btn._network_missing
                      or btn._network_forgetting or btn.network.security_type == SecurityType.UNSUPPORTED)
    assert btn.enabled != should_disable, \
      f"'{btn.network.ssid}': enabled={btn.enabled}, connecting={btn._is_connecting}, " \
      f"connected={btn._is_connected}, missing={btn._network_missing}, " \
      f"forgetting={btn._network_forgetting}, security={btn.network.security_type}"


# -- Hypothesis strategies --

SSID_ST = st.text(min_size=1, max_size=20)
NETWORK_ST = st.builds(Network, ssid=SSID_ST, strength=st.integers(0, 100),
                       security_type=st.sampled_from(list(SecurityType)), is_tethering=st.booleans())
NETWORKS_ST = st.lists(NETWORK_ST, max_size=8, unique_by=lambda n: n.ssid)


@st.composite
def WIFI_SCENARIOS(draw):
  networks = draw(NETWORKS_ST)
  ssids = [n.ssid for n in networks]
  status = draw(st.sampled_from(list(ConnectStatus)))
  ipv4 = draw(st.text(max_size=40))
  ssid = draw(st.one_of(st.sampled_from(ssids), SSID_ST, st.none())) if ssids else draw(st.one_of(SSID_ST, st.none()))
  saved = draw(st.frozensets(st.sampled_from(ssids) if ssids else st.nothing(), max_size=len(ssids)))
  return networks, WifiState(ssid=ssid, status=status), ipv4, saved


@st.composite
def EAGER_SCENARIOS(draw):
  initial = draw(st.lists(NETWORK_ST, min_size=1, max_size=6, unique_by=lambda n: n.ssid))
  known_ssids = [n.ssid for n in initial]
  actions = []

  for _ in range(draw(st.integers(1, 25))):
    action = draw(st.sampled_from([
      'network_update', 'need_auth', 'forgotten', 'forget_btn',
      'connect', 'disconnect', 'set_connected',
    ]))
    if action == 'network_update':
      nets = draw(st.lists(NETWORK_ST, max_size=6, unique_by=lambda n: n.ssid))
      actions.append(('network_update', nets))
      known_ssids = [n.ssid for n in nets]
    elif action == 'disconnect':
      actions.append(('disconnect',))
    elif known_ssids:
      actions.append((action, draw(st.sampled_from(known_ssids))))

  return initial, actions


class TestWifiUIInvariants(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    gui_app.init_window("test-wifi-invariants")
    cls.wm = FakeWifiManager()
    cls.net_btn = WifiNetworkButton(cls.wm)  # main settings page button, compared against WifiButtons inside wifi_ui
    cls.wifi_ui = WifiUIMici(cls.wm)

  @classmethod
  def tearDownClass(cls):
    gui_app.close()

  def _reset(self):
    self.wm.wifi_state = WifiState()
    self.wm._networks = []
    self.wm.ipv4_address = ""
    self.wm._saved_ssids = set()
    self.wifi_ui._scroller.items.clear()
    self.wifi_ui._networks.clear()

  @given(scenario=WIFI_SCENARIOS())
  @settings(max_examples=500, deadline=None, phases=(Phase.reuse, Phase.generate, Phase.shrink))
  def test_connection_status_consistent(self, scenario):
    """WifiNetworkButton and WifiButtons must agree on which network is active."""
    networks, wifi_state, ipv4, saved = scenario
    self._reset()

    self.wm.wifi_state = wifi_state
    self.wm._networks = networks
    self.wm.ipv4_address = ipv4
    self.wm._saved_ssids = set(saved)

    self.wifi_ui._on_network_updated(networks)
    self.net_btn._update_state()
    buttons = _get_buttons(self.wifi_ui)
    for btn in buttons.values():
      btn._update_state()

    active = wifi_state.ssid
    connecting = [b for b in buttons.values() if b._is_connecting]
    connected = [b for b in buttons.values() if b._is_connected]

    assert len(connecting) <= 1
    assert len(connected) <= 1
    for btn in buttons.values():
      assert not (btn._is_connecting and btn._is_connected)

    # Cross-widget: both must show the same ssid text
    if connecting:
      assert self.net_btn.text == connecting[0].text
    if connected:
      assert self.net_btn.text == connected[0].text

    # Converse: active ssid's button must reflect the status
    if active and active in buttons:
      if wifi_state.status == ConnectStatus.CONNECTING:
        assert buttons[active]._is_connecting
      elif wifi_state.status == ConnectStatus.CONNECTED:
        assert buttons[active]._is_connected

    # No non-active button should claim active
    for ssid, btn in buttons.items():
      if ssid != active:
        assert not btn._is_connecting, f"'{ssid}' claims connecting but active is '{active}'"
        assert not btn._is_connected, f"'{ssid}' claims connected but active is '{active}'"

    _check_disabled_invariant(buttons)

  @given(scenario=EAGER_SCENARIOS())
  @settings(max_examples=500, deadline=None, phases=(Phase.reuse, Phase.generate, Phase.shrink))
  def test_eager_state_interactions(self, scenario):
    """Eager state flags behave correctly through callback-driven sequences."""
    initial, actions = scenario
    self._reset()
    self.wifi_ui._on_network_updated(initial)

    for action_tuple in actions:
      action = action_tuple[0]
      buttons = _get_buttons(self.wifi_ui)

      if action == 'network_update':
        new_networks = action_tuple[1]
        new_ssids = {n.ssid for n in new_networks}
        wrong_pw_before = {s: b._wrong_password for s, b in buttons.items() if s in new_ssids}

        self.wifi_ui._on_network_updated(new_networks)

        for ssid, btn in _get_buttons(self.wifi_ui).items():
          if ssid in new_ssids:
            assert not btn._network_missing
            if btn._is_connected or btn._is_connecting:
              assert not btn._wrong_password
            elif ssid in wrong_pw_before:
              assert btn._wrong_password == wrong_pw_before[ssid]
          else:
            assert btn._network_missing

        ssids = [b.network.ssid for b in self.wifi_ui._scroller.items if isinstance(b, WifiButton)]
        assert len(ssids) == len(set(ssids)), f"Duplicate SSIDs: {ssids}"

      elif action == 'need_auth':
        btn = buttons.get(action_tuple[1])
        self.wifi_ui._on_need_auth(action_tuple[1])
        if btn is not None:
          assert btn._wrong_password

      elif action == 'forgotten':
        btn = buttons.get(action_tuple[1])
        self.wifi_ui._on_forgotten(action_tuple[1])
        if btn is not None:
          assert not btn._network_forgetting

      elif action == 'forget_btn':
        btn = buttons.get(action_tuple[1])
        if btn is not None:
          btn._forget_network()
          assert btn._network_forgetting

      elif action == 'connect':
        self.wm.wifi_state = WifiState(ssid=action_tuple[1], status=ConnectStatus.CONNECTING)

      elif action == 'disconnect':
        self.wm.wifi_state = WifiState()

      elif action == 'set_connected':
        self.wm.wifi_state = WifiState(ssid=action_tuple[1], status=ConnectStatus.CONNECTED)

      for btn in _get_buttons(self.wifi_ui).values():
        btn._update_state()
      _check_disabled_invariant(_get_buttons(self.wifi_ui))


  @given(scenario=EAGER_SCENARIOS())
  @settings(max_examples=500, deadline=None, phases=(Phase.reuse, Phase.generate, Phase.shrink))
  def test_no_crashes(self, scenario):
    """Random callback sequences must never crash, regardless of ordering or state."""
    initial, actions = scenario
    print((initial, actions))
    print()
    print()
    self._reset()
    self.wifi_ui._on_network_updated(initial)

    for action_tuple in actions:
      action = action_tuple[0]
      buttons = _get_buttons(self.wifi_ui)

      if action == 'network_update':
        self.wifi_ui._on_network_updated(action_tuple[1])
      elif action == 'need_auth':
        self.wifi_ui._on_need_auth(action_tuple[1])
      elif action == 'forgotten':
        self.wifi_ui._on_forgotten(action_tuple[1])
      elif action == 'forget_btn':
        btn = buttons.get(action_tuple[1])
        if btn is not None:
          btn._forget_network()
      elif action == 'connect':
        self.wm.wifi_state = WifiState(ssid=action_tuple[1], status=ConnectStatus.CONNECTING)
      elif action == 'disconnect':
        self.wm.wifi_state = WifiState()
      elif action == 'set_connected':
        self.wm.wifi_state = WifiState(ssid=action_tuple[1], status=ConnectStatus.CONNECTED)

      # Just update everything -- the only assertion is that nothing throws
      self.net_btn._update_state()
      for btn in _get_buttons(self.wifi_ui).values():
        btn._update_state()


if __name__ == "__main__":
  unittest.main()
