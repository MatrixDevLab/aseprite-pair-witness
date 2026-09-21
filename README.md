# Aseprite Pair Witness

`aseprite-pair-witness` is a small, dependency-free preflight for the boundary
between an Aseprite sprite-sheet PNG and its JSON metadata sidecar.

## Problem statement

Aseprite can export the image and metadata as separate files. A current export
bug report describes a failure mode where the PNG is written but the JSON path
is invalid after switching projects. Downstream consumers then receive an
incomplete animation asset rather than a single failed export.

The witness is intentionally narrower than an exporter, engine importer, or
JSON Schema package. It checks whether the two files form a usable pair:

- the JSON is parseable and has frame descriptors;
- the referenced PNG exists and is a readable PNG;
- frame rectangles are non-empty and within the PNG bounds;
- frame names and JSON member names are not ambiguous;
- the metadata image reference is portable and agrees with an explicitly
  supplied image.

It does not execute Aseprite, render frames, inspect animation semantics, or
replace a game-engine importer.

## Usage

```bash
python3 -m aseprite_pair_witness.cli --json build/player.json --image build/player.png --pretty
# Audit same-stem PNG/JSON sidecars in a build directory.
python3 -m aseprite_pair_witness.cli --directory build/assets --pretty
```

The report is deterministic JSON with a typed `status`:

- `pass`: the pair passed all checks;
- `warning`: the pair is usable but contains a portability risk;
- `fail`: a concrete pair or geometry invariant is false;
- `insufficient`: the witness cannot establish the pair invariant.

Exit code `0` is reserved for `pass`. Warnings return `1`; fail returns `1`;
insufficient returns `2`.

## Validation method

The first version has no runtime dependencies. Its tests use a minimal PNG
fixture and cover hash and array JSON forms, missing images, geometry bounds,
absolute path warnings, fail-closed missing metadata, and directory audits
that detect orphaned PNG or JSON sidecars.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

## Roadmap

1. Add opt-in checks for Aseprite `meta.size`, trimmed/rotated frame semantics,
   and selected slice/tag references.
2. Stop unless an independent consumer demonstrates a concrete need beyond
   these portable pair invariants.

## Stopping point

This release stops at static pair admission and loss-risk reporting. It does
not become a general Aseprite parser, a renderer, an asset packer, or an
engine-specific import replacement.
