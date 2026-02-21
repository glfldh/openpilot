import os
import capnp
from importlib.resources import as_file, files

capnp.remove_import_hook()

# Ensure car.capnp symlink exists (source of truth is opendbc package)
with as_file(files("cereal")) as fspath:
  CEREAL_PATH = fspath.as_posix()
  car_capnp = os.path.join(CEREAL_PATH, "car.capnp")
  if not os.path.exists(car_capnp):
    import opendbc
    os.symlink(os.path.join(os.path.dirname(opendbc.__file__), 'car', 'car.capnp'), car_capnp)
  log = capnp.load(os.path.join(CEREAL_PATH, "log.capnp"))
  car = capnp.load(os.path.join(CEREAL_PATH, "car.capnp"))
  custom = capnp.load(os.path.join(CEREAL_PATH, "custom.capnp"))
