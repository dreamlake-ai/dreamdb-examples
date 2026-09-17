# Local LLFF → Rerun and LanceDB

**Status: companion converter; current dependencies unverified.** This script
reads local LLFF files and writes Rerun recordings plus LanceDB tables. It does
not import DreamDB or accept a DreamDB backend. An older README advertised a
`--backend` path absent from the current script; that claim has been removed.

See the [application catalog](../README.md) for DreamDB-backed references.

## Input and output

Input is a scene directory containing `poses_bounds.npy` and optionally images,
or a parent directory containing several scenes. The application converts
camera conventions, records poses/images over a frame timeline and writes
per-scene `.rrd` and `.lance` outputs. These are converter-owned semantics.

## Historical execution path

The following matches the script's imports and CLI signature; it was not
runtime-tested during reorganization. Use a separate environment and a new
output directory: the converter does not enforce create-only publication.

```sh
pip install rerun-sdk lancedb params-proto numpy Pillow
python visualize_llff.py --data-dir /path/to/llff-scene --output-dir /new/output
```

The CLI also declares `no_images` and `spawn` options; check the installed
`params-proto` help for boolean flag syntax. The default spawns the viewer,
which requires a suitable desktop environment.

No LLFF input data is downloaded by this command. Outputs remain in the chosen
directory; remove only your generated output, not the input dataset. Current
Rerun/LanceDB compatibility and rendering remain unverified.
