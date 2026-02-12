import pickle
import hashlib
from pathlib import Path

def load_external_pickle(parts_path):
  parts_txt = Path(parts_path)

  lines = [x.strip() for x in parts_txt.read_text().splitlines() if x.strip()]

  meta = {}
  i = 0
  while i < len(lines) and "=" in lines[i]:
    k, v = lines[i].split("=", 1)
    meta[k] = v
    i += 1

  # remaining lines: "<filename> <hash>"
  part_lines = lines[i:]
  parts = [ln.split(None, 1)[0] for ln in part_lines]

  b = b"".join((parts_txt.parent / fn).read_bytes() for fn in parts)

  if len(b) != int(meta["len"]) or hashlib.blake2b(b, digest_size=16).hexdigest() != meta["hash"]:
    raise ValueError("checksum mismatch")

  return pickle.loads(b)
