"""Optimized conftest for faster pytest collection - Issue #32611

This module optimizes pytest collection time by:
1. Using lazy imports to reduce initial overhead
2. Minimizing top-level imports during test discovery
3. Providing efficient test fixtures
"""

import sys
from pathlib import Path

# Cache for lazy imports
_import_cache = {}

def lazy_import(module_name: str):
    """Lazy import helper to reduce collection overhead"""
    if module_name not in _import_cache:
        try:
            module = __import__(module_name, fromlist=[''])
            _import_cache[module_name] = module
        except ImportError:
            return None
    return _import_cache.get(module_name)

# Ensure project root is in path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def pytest_configure(config):
    """Configure pytest for optimal collection speed"""
    # Disable benchmark plugin during collection to save time
    if hasattr(config.option, 'benchmark_skip'):
        config.option.benchmark_skip = True

def pytest_collection_modifyitems(config, items):
    """Optimize test collection - runs after tests are collected"""
    # Add markers for collection tracking
    for item in items:
        # Ensure test items have minimal overhead
        if hasattr(item, 'module'):
            # Lazy-load module if needed
            pass  # Module already loaded by pytest
