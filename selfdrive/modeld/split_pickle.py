#!/usr/bin/env python3
"""Create a pickle pointer file with external data parts. Usage: split_pickle.py <input> <output>"""
import sys
from openpilot.selfdrive.modeld.external_pickle import dump_external_pickle, load_external_pickle

input_path = sys.argv[1]
output_path = sys.argv[2] if len(sys.argv) > 2 else input_path
obj = load_external_pickle(input_path)
dump_external_pickle(obj, output_path)
