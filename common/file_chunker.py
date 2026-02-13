import hashlib
import math
import os
from pathlib import Path

CHUNK_SIZE = 45 * 1024 * 1024
MANIFEST_SUFFIX = ".parts"
CHUNK_SUFFIX_FMT = ".chunk{idx:02d}"

def get_num_chunks(file_size: int) -> int:
  return math.ceil(file_size / CHUNK_SIZE) + 1

def chunk_file(path: str, num_chunks: int | None = None) -> str:
  p = Path(path)
  data = p.read_bytes()

  h = hashlib.sha256(data).hexdigest()
  total_len = len(data)

  actual_num_chunks = max(1, math.ceil(total_len / CHUNK_SIZE))
  if num_chunks is None:
    num_chunks = actual_num_chunks
  assert num_chunks >= actual_num_chunks, (
    f"expected {num_chunks} chunks but data needs at least {actual_num_chunks}"
  )

  chunk_names: list[str] = []
  for i in range(num_chunks):
    chunk_name = p.name + CHUNK_SUFFIX_FMT.format(idx=i)
    chunk_path = p.with_name(chunk_name)
    chunk_path.write_bytes(data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE])
    if i < actual_num_chunks:
      chunk_names.append(chunk_name)

  manifest_path = str(p) + MANIFEST_SUFFIX
  with open(manifest_path, "w", encoding="utf-8") as mf:
    mf.write("v=1\n")
    mf.write(f"chunk={CHUNK_SIZE}\n")
    mf.write(f"len={total_len}\n")
    mf.write(f"hash={h}\n")
    for name in chunk_names:
      mf.write(name + "\n")

  os.remove(str(p))
  return manifest_path


def read_file_chunked(path: str, verify: bool = True) -> bytes:
  p = Path(path)
  manifest = Path(str(p) + MANIFEST_SUFFIX)

  if not manifest.exists():
    if p.exists():
      return p.read_bytes()
    raise FileNotFoundError(str(p))

  expected_len = None
  expected_hash = None
  chunk_files: list[Path] = []

  for raw in manifest.read_text(encoding="utf-8").splitlines():
    ln = raw.strip()
    if not ln:
      continue
    if "=" in ln:
      k, v = ln.split("=", 1)
      k, v = k.strip(), v.strip()
      if k == "len":
        expected_len = int(v)
      elif k == "hash":
        expected_hash = v.lower()
      continue
    chunk_files.append(manifest.with_name(ln))

  data = b"".join(cf.read_bytes() for cf in chunk_files)

  if verify:
    if expected_len is not None and len(data) != expected_len:
      raise ValueError(f"checksum mismatch: len {len(data)} != expected {expected_len}")
    if expected_hash is not None:
      got = hashlib.sha256(data).hexdigest()
      if got != expected_hash:
        raise ValueError(f"checksum mismatch: sha256 {got} != expected {expected_hash}")

  return data
