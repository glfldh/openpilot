#!/usr/bin/env python3
"""Split a pickle file produced by compile3.py into external parts, then remove the original."""
import sys
from openpilot.selfdrive.modeld.external_pickle import dump_external_pickle, load_external_pickle

path = sys.argv[1]
obj = load_external_pickle(path)
dump_external_pickle(obj, path)
