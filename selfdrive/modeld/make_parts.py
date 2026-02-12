#!/usr/bin/env python3
import sys, math, hashlib
from pathlib import Path

raw = Path(sys.argv[1])
parts_txt = Path(sys.argv[2])
prefix = sys.argv[3]
chunk = int(sys.argv[4])

b = raw.read_bytes()
h_all = hashlib.blake2b(b, digest_size=16).hexdigest()

n = max(1, math.ceil(len(b) / chunk))

def part_name(i: int) -> str:
  return f"{prefix}.data-{i:03d}"

parts = []
for i in range(1, n + 1):
  off = (i - 1) * chunk
  part_bytes = b[off:off + chunk]
  h_part = hashlib.blake2b(part_bytes, digest_size=16).hexdigest()
  parts.append((part_name(i), h_part))

# prune any stale parts for this prefix
expected = {name for (name, _) in parts}
for f in parts_txt.parent.glob(prefix + ".data-*"):
  if f.name not in expected:
    f.unlink()

# header + parts (filename + hash)
parts_txt.write_text(
  "v=1\n"
  f"chunk={chunk}\n"
  f"len={len(b)}\n"
  f"hash={h_all}\n"
  + "\n".join(f"{name} {h_part}" for (name, h_part) in parts)
  + "\n"
)
