import hashlib, pickle
from pathlib import Path

def dump_external_pickle(obj, path, chunk=45*1024*1024):
  p = Path(path)
  b = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
  for x in p.parent.glob(p.name + ".data-*"):
    x.unlink()

  parts = []
  for i, off in enumerate(range(0, len(b), chunk), 1):
    fn = f"{p.name}.data-{i:03d}"
    (p.parent / fn).write_bytes(b[off:off+chunk])
    parts.append(fn)

  p.write_bytes(pickle.dumps({"_pickle_pointer_v1": True, "parts": parts, "sha256": hashlib.sha256(b).hexdigest()},
                              protocol=pickle.HIGHEST_PROTOCOL))

def load_external_pickle(path):
  p = Path(path)
  x = pickle.loads(p.read_bytes())
  if isinstance(x, dict) and x.get("_pickle_pointer_v1"):
    b = b"".join((p.parent / fn).read_bytes() for fn in x["parts"])
    assert hashlib.sha256(b).hexdigest() == x["sha256"], "external pickle hash mismatch"
    return pickle.loads(b)
  return x
