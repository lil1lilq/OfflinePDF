"""BUILD TIME ONLY: collect AGPL dependency sources for offline redistribution.

The application never imports this module. Archives remain unmodified.
"""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def download(url, path):
    temporary = path.with_suffix(path.suffix + ".partial")
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / "dependency-sources"
    out.mkdir(exist_ok=True)
    manifest = out / "sources.json"
    if args.offline:
        if not manifest.is_file():
            raise SystemExit("Run prepare_dependency_sources.py on an online preparation PC first.")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        required = {
            "pillow-13.0.0.tar.gz",
            "pillow_heif-1.8.1.tar.gz",
            "libheif-1.23.6-source.tar.gz",
            "libde265-1.1.3-source.tar.gz",
            "x265-e9b8812-source.tar.gz",
        }
        if not required <= {record["filename"] for record in data}:
            raise SystemExit(
                "Image dependency sources are missing. Prepare dependency sources online again."
            )
        for record in data:
            path = out / record["filename"]
            if not path.is_file() or digest(path) != record["sha256"]:
                raise SystemExit("Missing or altered source archive: " + record["filename"])
        return
    records = []
    for package, version in [("PyMuPDF", "1.26.6"), ("Pillow", "13.0.0"), ("pillow-heif", "1.8.1")]:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{package}/{version}/json", timeout=30
        ) as response:
            release = json.load(response)
        source = next(item for item in release["urls"] if item["packagetype"] == "sdist")
        records.append(
            {
                "filename": source["filename"],
                "url": source["url"],
                "sha256": source["digests"]["sha256"],
            }
        )
    records += [
        {
            "filename": "mupdf-1.26.11-source.tar.gz",
            "url": "https://mupdf.com/downloads/archive/mupdf-1.26.11-source.tar.gz",
        },
        {
            "filename": "libheif-1.23.6-source.tar.gz",
            "url": "https://github.com/strukturag/libheif/archive/refs/tags/v1.23.6.tar.gz",
        },
        {
            "filename": "libde265-1.1.3-source.tar.gz",
            "url": "https://github.com/strukturag/libde265/archive/refs/tags/v1.1.3.tar.gz",
        },
        {
            "filename": "x265-e9b8812-source.tar.gz",
            "url": "https://github.com/Multicorewareinc/x265/archive/e9b8812.tar.gz",
        },
    ]
    for record in records:
        path = out / record["filename"]
        if not path.is_file():
            download(record["url"], path)
        actual = digest(path)
        if record.get("sha256") and actual != record["sha256"]:
            raise SystemExit("Source archive checksum mismatch.")
        record["sha256"] = actual
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Dependency source archives prepared. Include this directory alongside the binaries.")


if __name__ == "__main__":
    main()
