# Release-readiness snapshot

Review date: 2026-09-22

This snapshot records the bounded evidence used for the post-v1 release and
stopping decision. It is not a claim of installation compatibility on every
packaging toolchain.

## Checks completed

- The ten repository unit tests pass.
- `python3 -m compileall -q src tests` passes.
- `git diff --check` passes.
- Setuptools metadata preparation succeeds for version `0.1.0`, including the
  SPDX `MIT` license metadata.
- A wheel-install smoke test was not run: `pip` is not available in the
  current environment.

## Consumer boundary

- [Aseprite issue #6040](https://github.com/aseprite/aseprite/issues/6040)
  remains open. Its current report still describes a PNG export succeeding
  while the JSON sidecar path fails after switching projects; the visible
  discussion does not establish a new portable invariant.
- [auto-godot issue #135](https://github.com/Wundrfull/auto-godot/issues/135)
  remains open with no comments. Its reported generated-path mismatch supports
  the existing pair/path failure boundary, but its proposed copy behavior is
  engine-specific.

## Decision

The current implementation is release-ready within its declared scope:
static PNG/JSON pair admission, frame and JSON-shape checks, and deterministic
directory orphan reporting. No new portable check or engine integration is
supported by the current consumer evidence. The project remains stopped at
this boundary pending a new independent consumer requirement or concrete
failure report outside the existing checks.

The unavailable pip smoke test is an explicit validation gap, not evidence of
failure. No packaging or runtime claim should be broadened until that check is
run in an environment that provides pip.
