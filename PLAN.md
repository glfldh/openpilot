# High-Level Goals (from user)

1. Migrate Cabana from Qt to dearpygui.
2. Use GUI helper libraries so we do not have to build every GUI piece from scratch.
3. Plan a DearPyGui frontend with a Cython interop layer to reuse existing C++ code.
4. Performance is critical and we cannot regress performance.
5. we must maintain all existing features too, the only goal here is to delete Qt from this repo.

# Notes and Execution Plan

## 1) Scope and Direction

- Keep the hot data path in C++ and keep Python UI thin.
- Use DearPyGui for the new UI layer, while preserving a backend architecture that can support other frontends later.
- Reuse proven C++ replay/stream/DBC logic instead of re-implementing it in Python.
- Maintain feature parity with current Cabana in phases, with hard performance gates at each phase.

## 2) Non-Negotiable Performance Rules

- No per-event Python object creation for CAN events.
- No Python in tight loops for decode, signal extraction, bit-flip accumulation, or chart point generation.
- Cython boundary is batch-oriented (snapshots/diffs), not callback-per-event.
- Use preallocated buffers and typed memoryviews for low-overhead interop.
- Every milestone must meet or exceed baseline performance on agreed workloads.

## 3) Proposed Architecture

### 3.1 C++ backend (`cabana_core`)

- Extract and/or reuse from:
  - `tools/cabana/streams/abstractstream.cc`
  - `tools/cabana/streams/replaystream.cc`
  - `tools/cabana/dbc/dbc.cc`
  - `tools/cabana/dbc/dbcfile.cc`
  - `tools/replay/replay.cc`
- Provide Qt-free core services:
  - Route load, play/pause/seek/speed
  - Message state snapshots (freq/count/last bytes/colors/active state)
  - Binary grid data and bit-flip heatmap data
  - Signal decode values and sparkline-ready ranges
  - Chart series generation + decimation/min-max bucketing
  - DBC CRUD + validation
  - Undo/redo command engine

### 3.2 C API shim

- Expose opaque handles and POD structs only.
- Export batched APIs such as:
  - `cabana_get_messages_snapshot(...)`
  - `cabana_get_binary_view(...)`
  - `cabana_get_signal_values(...)`
  - `cabana_get_chart_points_decimated(...)`
  - DBC mutation APIs + undo/redo APIs
- Keep API stable and versioned for the Python side.

### 3.3 Cython extension

- Use `cdef extern from` against the C API.
- Use `with nogil` around heavy backend calls.
- Convert C buffers to Python via memoryviews/NumPy with minimal copying.
- Keep wrapper code mostly mechanical (no business logic in Cython).

### 3.4 DearPyGui frontend

- UI responsibilities only:
  - Panels/layout
  - Input handling
  - View state
  - Render of precomputed datasets
- Data flow model:
  - Poll backend at frame tick for deltas/snapshots
  - Render from immutable frame data
  - Send user intents as coarse backend commands

## 4) Milestones

### M0 - Baseline and perf harness

- Define canonical benchmark routes and interaction scripts.
- Capture current Qt Cabana baseline:
  - startup time
  - route load time
  - seek latency
  - frame/update rate
  - CPU and memory
  - chart interaction latency
- Add repeatable benchmark command(s) and report format.

### M1 - Core extraction + C API skeleton

- Build Qt-free core playback/stream/message snapshot path.
- C API for route load/play/seek and message snapshots.
- Verify parity for basic playback state against Qt app.

### M2 - Cython bindings + smoke tests

- Create Cython module target in SCons.
- Add smoke tests for load/play/seek/snapshot APIs.
- Validate zero/low-copy path and GIL behavior.

### M3 - DearPyGui MVP (read-only)

- Stream open/load route UI
- Message list (virtualized)
- Binary view (read-only)
- Signal value list (read-only)
- Basic timeline controls
- Perf gate vs baseline on message-heavy routes.

### M4 - Charts and timeline quality

- Multi-series plots with backend decimation.
- Zoom, pan, scrub, and hover value display.
- Time-range filtering equivalent to existing behavior.
- Perf gate for chart-heavy usage (no regression).

### M5 - Editing and command stack

- DBC message/signal CRUD in new UI.
- Undo/redo parity.
- Save/save-as/clipboard parity.
- Validation and error paths.

### M6 - Advanced tools and source parity

- Find Signal
- Find Similar Bits
- Export CSV
- Live sources (msgq/zmq/panda/socketcan)

### M7 - Stabilization and cutover

- Full regression suite + perf suite pass.
- User workflow parity checklist complete.
- Keep Qt version available behind a build/runtime switch during rollout.

## 5) Performance Gates (must pass)

- Startup and route load: no slower than baseline.
- Seek latency (p50/p95): no slower than baseline.
- UI update cadence under replay load: no dropped-frame regression.
- CPU and memory under same workload: no regression.
- Chart operations (zoom/pan/hover): no latency regression.

If any gate fails, optimize before moving to the next milestone.

## 6) Key Risks and Mitigations

- DearPyGui large-table overhead
  - Mitigation: strict virtualization and incremental updates.
- Python boundary overhead
  - Mitigation: batched C APIs and memoryviews, no event-by-event callbacks.
- Chart data explosion
  - Mitigation: C++ decimation before UI rendering.
- Feature drift during migration
  - Mitigation: parity checklist and side-by-side validation with Qt Cabana.

## 7) Immediate Next Steps

1. Add baseline benchmark script and route set (M0).
2. Scaffold `cabana_core` and C API headers (M1).
3. Add initial Cython module build target and smoke test (M2).
4. Stand up DearPyGui shell that can load route and render message snapshot (M3 start).
