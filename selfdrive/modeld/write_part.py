#!/usr/bin/env python3
import re, sys
from pathlib import Path

parts_txt = Path(sys.argv[1])
raw = Path(sys.argv[2])
out = Path(sys.argv[3])

# Read chunk size from manifest header
for line in parts_txt.read_text().splitlines():
  line = line.strip()
  if line.startswith("chunk="):
    chunk = int(line.split("=", 1)[1])
    break
else:
  raise SystemExit("chunk= not found in manifest")

# Infer part index from target filename: "...data-001"
m = re.search(r"\.data-(\d+)$", out.name)
if not m:
  raise SystemExit(f"can't infer part index from target name: {out.name}")
idx = int(m.group(1))

off = (idx - 1) * chunk
out.parent.mkdir(parents=True, exist_ok=True)
with open(raw, "rb") as f:
  f.seek(off)
  out.write_bytes(f.read(chunk))
