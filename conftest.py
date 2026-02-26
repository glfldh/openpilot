"""Optimized conftest.py for faster pytest collection."""
import contextlib
import gc
import os
import pytest

# Lazy imports to speed up collection
_openpilot_prefix = None
_manager = None
_HARDWARE = None

def _get_prefix():
    global _openpilot_prefix
    if _openpilot_prefix is None:
        from openpilot.common.prefix import OpenpilotPrefix
        _openpilot_prefix = OpenpilotPrefix
    return _openpilot_prefix

def _get_manager():
    global _manager
    if _manager is None:
        from openpilot.system.manager import manager
        _manager = manager
    return _manager

def _get_hardware():
    global _HARDWARE
    if _HARDWARE is None:
        from openpilot.system.hardware import HARDWARE
        _HARDWARE = HARDWARE
    return _HARDWARE

# TODO: pytest-cpp doesn't support FAIL, and we need to create test translations in sessionstart
# pending https://github.com/pytest-dev/pytest-cpp/pull/147
collect_ignore = [
  "selfdrive/ui/tests/test_translations",
  "selfdrive/test/process_replay/test_processes.py",
  "selfdrive/test/process_replay/test_regen.py",
]
collect_ignore_glob = [
  "selfdrive/debug/*.py",
  "selfdrive/modeld/*.py",
]


def pytest_sessionstart(session):
  # TODO: fix tests and enable test order randomization
  if session.config.pluginmanager.hasplugin('randomly'):
    session.config.option.randomly_reorganize = False


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_call(item):
  # ensure we run as a hook after capturemanager's
  if item.get_closest_marker("nocapture") is not None:
    capmanager = item.config.pluginmanager.getplugin('capturemanager')
    with capmanager.global_and_fixture_disabled():
      yield
  else:
    yield


@contextlib.contextmanager
def clean_env():
  starting_env = dict(os.environ)
  yield
  os.environ.clear()
  os.environ.update(starting_env)


@pytest.fixture(scope="function", autouse=True)
def openpilot_function_fixture(request):
  with clean_env():
    yield
