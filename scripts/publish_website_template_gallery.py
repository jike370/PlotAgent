"""Publish a verified gallery build as compressed static website assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

REPOSITORY = Path(__file__).resolve().parents[1]


def _relative_sample(raw: str) -> str:
    path = Path(raw)
    parts = path.parts
    for marker in ("Graphing", "Signal Processing", "Statistics"):
        if marker in parts:
            return "/".join(parts[parts.index(marker) :])
    return path.name


def _webp(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((1024, 768), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "WEBP", quality=84, method=6)


def publish(build: Path, target: Path) -> None:
    build = build.resolve()
    target = target.resolve()
    if target.exists():
        raise FileExistsError(f"refusing to overwrite gallery target: {target}")
    target.mkdir(parents=True)

    raw_manifest = json.loads((build / "gallery-manifest.json").read_text(encoding="utf-8"))
    failures = [row for row in raw_manifest if row.get("origin_error")]
    if failures:
        summary = ", ".join(f"{row['profile_id']}: {row['origin_error']}" for row in failures)
        raise RuntimeError(f"gallery contains Origin failures: {summary}")

    public_manifest = []
    for row in raw_manifest:
        profile_id = row["profile_id"]
        matplotlib_source = build / row["matplotlib_png"]
        origin_source = build / row["origin_png"]
        if not matplotlib_source.is_file() or not origin_source.is_file():
            raise FileNotFoundError(f"{profile_id} is missing one backend image")
        _webp(matplotlib_source, target / f"{profile_id}-matplotlib.webp")
        _webp(origin_source, target / f"{profile_id}-origin.webp")
        public_manifest.append(
            {
                "profile_id": profile_id,
                "chinese_name": row["chinese_name"],
                "official_name": row["official_name"],
                "official_help_url": row["official_help_url"],
                "official_entry": row["official_entry"],
                "origin_templates": row["origin_templates"],
                "origin_sample": _relative_sample(row["origin_sample"]),
                "sample_adaptation": row["sample_adaptation"],
            }
        )

    (target / "manifest.json").write_text(
        json.dumps(public_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument(
        "--target",
        type=Path,
        default=REPOSITORY / "website" / "assets" / "templates" / "gallery",
    )
    args = parser.parse_args()
    publish(args.build, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
