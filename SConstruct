import os
import subprocess
import sys
import sysconfig
import platform
import shlex
import numpy as np
import opendbc
import panda as _panda
import rednose
import msgq as _msgq

import SCons.Errors

SCons.Warnings.warningAsException(True)

Decider('MD5-timestamp')

SetOption('num_jobs', max(1, int(os.cpu_count()/2)))

AddOption('--asan', action='store_true', help='turn on ASAN')
AddOption('--ubsan', action='store_true', help='turn on UBSan')
AddOption('--mutation', action='store_true', help='generate mutation-ready code')
AddOption('--ccflags', action='store', type='string', default='', help='pass arbitrary flags over the command line')
AddOption('--minimal',
          action='store_false',
          dest='extras',
          default=os.path.exists(File('#.gitattributes').abspath), # minimal by default on release branch (where there's no LFS)
          help='the minimum build to run openpilot. no tests, tools, etc.')

# Detect platform
arch = subprocess.check_output(["uname", "-m"], encoding='utf8').rstrip()
if platform.system() == "Darwin":
  arch = "Darwin"
  brew_prefix = subprocess.check_output(['brew', '--prefix'], encoding='utf8').strip()
elif arch == "aarch64" and os.path.isfile('/TICI'):
  arch = "larch64"
assert arch in [
  "larch64",  # linux tici arm64
  "aarch64",  # linux pc arm64
  "x86_64",   # linux pc x64
  "Darwin",   # macOS arm64 (x86 not supported)
]

env = Environment(
  ENV={
    "PATH": os.environ['PATH'],
    "PYTHONPATH": Dir("#").abspath + ':' + Dir(f"#third_party/acados").abspath,
    "ACADOS_SOURCE_DIR": Dir("#third_party/acados").abspath,
    "ACADOS_PYTHON_INTERFACE_PATH": Dir("#third_party/acados/acados_template").abspath,
    "TERA_PATH": Dir("#").abspath + f"/third_party/acados/{arch}/t_renderer"
  },
  CC='clang',
  CXX='clang++',
  CCFLAGS=[
    "-g",
    "-fPIC",
    "-O2",
    "-Wunused",
    "-Werror",
    "-Wshadow",
    "-Wno-unknown-warning-option",
    "-Wno-inconsistent-missing-override",
    "-Wno-c99-designator",
    "-Wno-reorder-init-list",
    "-Wno-vla-cxx-extension",
  ],
  CFLAGS=["-std=gnu11"],
  CXXFLAGS=["-std=c++1z"],
  CPPPATH=[
    "#",
    _msgq.INCLUDE_PATH,
    _panda.INCLUDE_PATH,
    rednose.BASEDIR,
    "#third_party",
    "#third_party/json11",
    "#third_party/linux/include",
    "#third_party/acados/include",
    "#third_party/acados/include/blasfeo/include",
    "#third_party/acados/include/hpipm/include",
    "#third_party/catch2/include",
    "#third_party/libyuv/include",
  ],
  LIBPATH=[
    "#common",
    "#third_party",
    "#selfdrive/pandad",
    rednose.HELPERS_PATH,
    f"#third_party/libyuv/{arch}/lib",
    f"#third_party/acados/{arch}/lib",
  ],
  RPATH=[],
  CYTHONCFILESUFFIX=".cpp",
  COMPILATIONDB_USE_ABSPATH=True,
  REDNOSE_ROOT=rednose.INCLUDE_PATH,
  tools=["default", "cython", "compilation_db", "rednose_filter"],
  toolpath=["#site_scons/site_tools", rednose.SITE_SCONS_TOOLS],
)

# Arch-specific flags and paths
if arch == "larch64":
  env.Append(LIBPATH=[
    "/usr/local/lib",
    "/system/vendor/lib64",
    "/usr/lib/aarch64-linux-gnu",
  ])
  arch_flags = ["-D__TICI__", "-mcpu=cortex-a57"]
  env.Append(CCFLAGS=arch_flags)
  env.Append(CXXFLAGS=arch_flags)
elif arch == "Darwin":
  env.Append(LIBPATH=[
    f"{brew_prefix}/lib",
    f"{brew_prefix}/opt/openssl@3.0/lib",
    f"{brew_prefix}/opt/llvm/lib/c++",
    "/System/Library/Frameworks/OpenGL.framework/Libraries",
  ])
  env.Append(CCFLAGS=["-DGL_SILENCE_DEPRECATION"])
  env.Append(CXXFLAGS=["-DGL_SILENCE_DEPRECATION"])
  env.Append(CPPPATH=[
    f"{brew_prefix}/include",
    f"{brew_prefix}/opt/openssl@3.0/include",
  ])
else:
  env.Append(LIBPATH=[
    "/usr/lib",
    "/usr/local/lib",
  ])

# Sanitizers and extra CCFLAGS from CLI
if GetOption('asan'):
  env.Append(CCFLAGS=["-fsanitize=address", "-fno-omit-frame-pointer"])
  env.Append(LINKFLAGS=["-fsanitize=address"])
elif GetOption('ubsan'):
  env.Append(CCFLAGS=["-fsanitize=undefined"])
  env.Append(LINKFLAGS=["-fsanitize=undefined"])

_extra_cc = shlex.split(GetOption('ccflags') or '')
if _extra_cc:
  env.Append(CCFLAGS=_extra_cc)

# no --as-needed on mac linker
if arch != "Darwin":
  env.Append(LINKFLAGS=["-Wl,--as-needed", "-Wl,--no-undefined"])

# progress output
node_interval = 5
node_count = 0
def progress_function(node):
  global node_count
  node_count += node_interval
  sys.stderr.write("progress: %d\n" % node_count)
if os.environ.get('SCONS_PROGRESS'):
  Progress(progress_function, interval=node_interval)

# ********** Cython build environment **********
py_include = sysconfig.get_paths()['include']
envCython = env.Clone()
envCython["CPPPATH"] += [py_include, np.get_include()]
envCython["CCFLAGS"] += ["-Wno-#warnings", "-Wno-shadow", "-Wno-deprecated-declarations"]
envCython["CCFLAGS"].remove("-Werror")

envCython["LIBS"] = []
if arch == "Darwin":
  envCython["LINKFLAGS"] = env["LINKFLAGS"] + ["-bundle", "-undefined", "dynamic_lookup"]
else:
  envCython["LINKFLAGS"] = ["-pthread", "-shared"]

np_version = SCons.Script.Value(np.__version__)
Export('envCython', 'np_version')

Export('env', 'arch')

# Setup cache dir
cache_dir = '/data/scons_cache' if arch == "larch64" else '/tmp/scons_cache'
CacheDir(cache_dir)
Clean(["."], cache_dir)

# ********** start building stuff **********

# Build common module
SConscript(['common/SConscript'])
Import('_common')
common = [_common, 'json11', 'zmq']
Export('common')

# Build messaging (cereal + msgq + socketmaster + their dependencies)
# Enable swaglog include in submodules
env_swaglog = env.Clone()
env_swaglog['CXXFLAGS'].append('-DSWAGLOG="\\"common/swaglog.h\\""')

# Build msgq from installed package
msgq_dir = _msgq.BASEDIR
vipc_dir = os.path.join(msgq_dir, 'visionipc')

msgq_sources = [os.path.join(msgq_dir, f) for f in
                ['ipc.cc', 'event.cc', 'impl_msgq.cc', 'impl_fake.cc', 'msgq.cc']]
msgq_objects = env_swaglog.SharedObject(msgq_sources)
msgq_lib = env.Library('msgq', msgq_objects)
msgq_python = envCython.Program(os.path.join(msgq_dir, 'ipc_pyx.so'),
                                os.path.join(msgq_dir, 'ipc_pyx.pyx'),
                                LIBS=envCython["LIBS"]+[msgq_lib, common])

vipc_files = ['visionipc.cc', 'visionipc_server.cc', 'visionipc_client.cc']
vipc_files += ['visionbuf_ion.cc'] if arch == "larch64" else ['visionbuf.cc']
vipc_sources = [os.path.join(vipc_dir, f) for f in vipc_files]
vipc_objects = env.SharedObject(vipc_sources)
visionipc = env.Library('visionipc', vipc_objects)
envCython.Program(os.path.join(vipc_dir, 'visionipc_pyx.so'),
                  os.path.join(vipc_dir, 'visionipc_pyx.pyx'),
                  LIBS=envCython["LIBS"] + [visionipc, msgq_lib, common])
Export('visionipc', 'msgq_lib', 'msgq_python')

SConscript(['cereal/SConscript'])

Import('socketmaster')
messaging = [socketmaster, msgq_lib, 'capnp', 'kj',]
Export('messaging')


# Build rednose library
Import('_common')
rednose_helpers = rednose.HELPERS_PATH
rednose_cc = [os.path.join(rednose_helpers, f) for f in ['ekf_load.cc', 'ekf_sym.cc']]
ekf_objects = env.SharedObject(rednose_cc)
rednose_lib = env.Library(os.path.join(rednose_helpers, 'ekf_sym'), ekf_objects, LIBS=['dl', _common, 'zmq'])
rednose_python = envCython.Program(os.path.join(rednose_helpers, 'ekf_sym_pyx.so'),
                                   [os.path.join(rednose_helpers, 'ekf_sym_pyx.pyx'), ekf_objects],
                                   LIBS=['dl'] + envCython["LIBS"])
Export('rednose_lib', 'rednose_python')

# Build opendbc libsafety for tests
safety_dir = os.path.join(os.path.dirname(opendbc.__file__), 'safety', 'tests', 'libsafety')
if GetOption('extras') and os.path.exists(os.path.join(safety_dir, 'safety.c')):
  safety_env = Environment(
    CC='clang',
    CFLAGS=['-Wall', '-Wextra', '-Werror', '-nostdlib', '-fno-builtin', '-std=gnu11',
            '-Wfatal-errors', '-Wno-pointer-to-int-cast', '-g', '-O0',
            '-fno-omit-frame-pointer', '-grecord-command-line', '-DALLOW_DEBUG'],
    LINKFLAGS=['-fsanitize=undefined', '-fno-sanitize-recover=undefined'],
    CPPPATH=[os.path.dirname(opendbc.__file__) + "/.."],
    tools=["default"],
  )
  safety = safety_env.SharedObject(os.path.join(safety_dir, "safety.os"), os.path.join(safety_dir, "safety.c"))
  safety_env.SharedLibrary(os.path.join(safety_dir, "libsafety.so"), [safety])

# Build system services
SConscript([
  'system/loggerd/SConscript',
])

if arch == "larch64":
  SConscript(['system/camerad/SConscript'])

# Build openpilot
SConscript(['third_party/SConscript'])

SConscript(['selfdrive/SConscript'])

if Dir('#tools/cabana/').exists() and arch != "larch64":
  SConscript(['tools/cabana/SConscript'])


env.CompilationDatabase('compile_commands.json')
