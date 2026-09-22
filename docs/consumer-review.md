# Post-v1 consumer review

Review date: 2026-09-21

This review checks whether the shipped static pair witness should grow another
portable invariant or an engine-specific integration.

## Evidence

- [Aseprite issue #6040](https://github.com/aseprite/aseprite/issues/6040)
  remains open as of 2026-09-22. Its reproduction still describes a PNG
  export succeeding while the JSON sidecar is absent after switching projects;
  the only maintainer-side discussion currently visible is a user report that
  disabling and re-enabling JSON export restored the behavior. This confirms
  the upstream failure boundary but does not add a new consumer requirement
  beyond the shipped pair-admission witness.
- [Phaser's Aseprite loader](https://docs.phaser.io/api-documentation/class/loader-loaderplugin)
  accepts separate texture and atlas URLs and documents an exported PNG/JSON
  pair. This is direct evidence that missing or mismatched sidecars are a
  meaningful downstream failure boundary.
- [Excalibur's Aseprite plugin](https://excaliburjs.com/docs/aseprite-plugin/)
  loads an Aseprite resource from JSON, providing an independent consumer
  shape for the same asset family.
- [Unity's 2D Aseprite importer](https://docs.unity3d.com/ja/Packages/com.unity.2d.aseprite@3.0/manual/index.html)
  is an engine-integrated `.aseprite` importer rather than a portable PNG/JSON
  sidecar validator. It is useful scope evidence, but not a reason to add a
  Unity-specific mode here.
- [auto-godot issue #135](https://github.com/Wundrfull/auto-godot/issues/135)
  reports a concrete downstream failure where an imported Aseprite JSON
  resource references a sheet PNG at a generated path while the exported PNG
  remains elsewhere, causing Godot validation to fail with a missing resource.
  This is independent evidence that pair/path relationships matter at a
  consumer boundary, but the proposed copy/path flags are Godot-specific and
  do not justify an engine integration here.

## Decision

The current boundary remains useful and sufficiently narrow:

- static pair admission and image-reference checks;
- frame geometry and JSON-shape checks;
- deterministic directory-level orphan detection;
- typed reports suitable for CI.

No additional portable invariant was supported by this review. The project
stops at pair admission and loss-risk reporting. Future expansion needs a new
independent consumer or a concrete failure report that is not already covered
by the current checks. In particular, this tool should not become an Aseprite
renderer, exporter, packer, general parser, or engine importer.
