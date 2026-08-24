#!/usr/bin/env python3
"""Bake YaRN rope-scaling metadata into a GGUF so llama.cpp/Ollama can serve a
context window larger than the model's trained length without attention decay.

Qwen2.5-Coder-7B (DeepHat's base) is trained at 32768 tokens and extends cleanly
with YaRN (the method the Qwen team recommends). Ollama's Modelfile does not
expose a rope-scaling type, but the llama.cpp core it runs reads the scaling
config straight from GGUF metadata keys:

    <arch>.rope.scaling.type                    = "yarn"
    <arch>.rope.scaling.factor                  = <factor>          (f32)
    <arch>.rope.scaling.original_context_length = <trained ctx>     (u32)

so writing them into the file is the robust, self-contained way to unlock a
bigger window. factor 2.0 -> 64K, 3.0 -> 96K, 4.0 -> 128K. Keep factor as small
as the target window needs: static YaRN trades a little short-context accuracy
for the extended range, and the penalty grows with the factor.

The transform streams tensor data straight through, so it needs no extra RAM for
the 8 GB of weights, only a second copy on disk. It is idempotent: re-running
with the same factor is a no-op.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Prefer the in-repo vendored gguf (installed under .wizards-pick/python by
# ollama-local.sh) so the build stays self-contained, then fall back to any gguf
# already importable.
_VENDOR = Path(__file__).resolve().parents[1] / ".wizards-pick" / "python"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))

import gguf  # noqa: E402

TYPE_KEY = "{arch}.rope.scaling.type"
FACTOR_KEY = "{arch}.rope.scaling.factor"
ORIG_CTX_KEY = "{arch}.rope.scaling.original_context_length"
CTX_LEN_KEY = "{arch}.context_length"


def _arch(reader: gguf.GGUFReader) -> str:
    field = reader.get_field(gguf.Keys.General.ARCHITECTURE)
    if field is None:
        raise SystemExit("GGUF has no general.architecture field")
    return str(field.contents())


def current_factor(path: Path) -> float | None:
    reader = gguf.GGUFReader(path, "r")
    arch = _arch(reader)
    ftype = reader.get_field(TYPE_KEY.format(arch=arch))
    ffac = reader.get_field(FACTOR_KEY.format(arch=arch))
    if ftype is None or ffac is None:
        return None
    if str(ftype.contents()).lower() != "yarn":
        return None
    return float(ffac.contents())


def bake(src: Path, dst: Path, factor: float, orig_ctx: int) -> None:
    reader = gguf.GGUFReader(src, "r")
    arch = _arch(reader)
    managed = {
        TYPE_KEY.format(arch=arch),
        FACTOR_KEY.format(arch=arch),
        ORIG_CTX_KEY.format(arch=arch),
        CTX_LEN_KEY.format(arch=arch),
    }
    extended_ctx = round(orig_ctx * factor)

    writer = gguf.GGUFWriter(dst, arch=arch, endianess=reader.endianess)

    for field in reader.fields.values():
        # GGUFWriter emits these itself; managed rope keys are (re)written below.
        if field.name == gguf.Keys.General.ARCHITECTURE or field.name.startswith("GGUF."):
            continue
        if field.name in managed:
            continue
        val_type = field.types[0]
        sub_type = field.types[-1] if val_type == gguf.GGUFValueType.ARRAY else None
        writer.add_key_value(field.name, field.contents(), val_type, sub_type=sub_type)

    # Advertise the extended window so Ollama does not clamp num_ctx back down to
    # the trained length; YaRN below rescales positions within it.
    writer.add_key_value(CTX_LEN_KEY.format(arch=arch), extended_ctx, gguf.GGUFValueType.UINT32)
    writer.add_key_value(TYPE_KEY.format(arch=arch), "yarn", gguf.GGUFValueType.STRING)
    writer.add_key_value(FACTOR_KEY.format(arch=arch), float(factor), gguf.GGUFValueType.FLOAT32)
    writer.add_key_value(ORIG_CTX_KEY.format(arch=arch), int(orig_ctx), gguf.GGUFValueType.UINT32)

    for tensor in reader.tensors:
        writer.add_tensor_info(
            tensor.name,
            tensor.data.shape,
            tensor.data.dtype,
            tensor.data.nbytes,
            tensor.tensor_type,
        )

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()
    for tensor in reader.tensors:
        writer.write_tensor_data(tensor.data, tensor_endianess=reader.endianess)
    writer.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake YaRN rope-scaling metadata into a GGUF.")
    ap.add_argument("gguf", type=Path, help="GGUF to tune (modified in place via a temp file)")
    ap.add_argument(
        "--factor", type=float, default=2.0, help="YaRN scale factor (2=64K, 3=96K, 4=128K)"
    )
    ap.add_argument("--orig-ctx", type=int, default=32768, help="model's trained context length")
    ap.add_argument("--output", type=Path, default=None, help="write here instead of in place")
    args = ap.parse_args()

    src: Path = args.gguf
    if not src.is_file():
        raise SystemExit(f"GGUF not found: {src}")

    if args.factor <= 1.0:
        print(f"factor {args.factor} <= 1: no rope scaling needed, leaving {src} untouched")
        return 0

    existing = current_factor(src)
    in_place = args.output is None
    if in_place and existing == float(args.factor):
        print(f"{src.name} already YaRN factor {args.factor}; nothing to do")
        return 0

    dst = args.output or src.with_suffix(src.suffix + ".tmp")
    print(f"baking YaRN factor {args.factor} (orig_ctx {args.orig_ctx}) -> {dst.name} ...")
    bake(src, dst, args.factor, args.orig_ctx)

    if in_place:
        os.replace(dst, src)
        print(f"tuned {src.name} in place (YaRN factor {args.factor})")
    else:
        print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
