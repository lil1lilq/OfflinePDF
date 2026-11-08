"""BUILD TIME ONLY: collect AGPL dependency sources for offline redistribution.

The application never imports this module. Archives remain unmodified.
"""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

MUPDF_SOURCE = "mupdf-1.26.12-source.tar.gz"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


# Source hosts such as mupdf.com sometimes answer 502/503/504 for a while;
# together these waits ride out about eight minutes. CI also caches the files.
RETRY_DELAYS = (10, 30, 60, 120, 240)


def retrying(action, url, sleep=time.sleep):
    """Run action(), retrying temporary network and server errors with growing waits."""
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return action()
        except urllib.error.HTTPError as exc:
            # 4xx other than "too many requests" will not fix itself: fail at once.
            if attempt == len(RETRY_DELAYS) or (exc.code < 500 and exc.code != 429):
                raise
            reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == len(RETRY_DELAYS):
                raise
            reason = type(exc).__name__
        delay = RETRY_DELAYS[attempt]
        print(f"{reason} from {url}; retrying in {delay} s ({attempt + 1}/{len(RETRY_DELAYS)})")
        sleep(delay)


def download(url, path):
    temporary = path.with_suffix(path.suffix + ".partial")

    def fetch():
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)

    try:
        retrying(fetch, url)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def fetch_json(url):
    def fetch():
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)

    return retrying(fetch, url)


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
            "pymupdf-1.26.7.tar.gz",
            "pillow-13.0.0.tar.gz",
            MUPDF_SOURCE,
        }
        if not required <= {record["filename"] for record in data}:
            raise SystemExit(
                "Dependency sources are missing. Prepare dependency sources online again."
            )
        for record in data:
            path = out / record["filename"]
            if not path.is_file() or digest(path) != record["sha256"]:
                raise SystemExit("Missing or altered source archive: " + record["filename"])
        return
    records = []
    for package, version in [("PyMuPDF", "1.26.7"), ("Pillow", "13.0.0")]:
        release = fetch_json(f"https://pypi.org/pypi/{package}/{version}/json")
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
            # The MuPDF release bundled in PyMuPDF 1.26.7 (pymupdf.VersionFitz).
            "filename": MUPDF_SOURCE,
            "url": "https://mupdf.com/downloads/archive/" + MUPDF_SOURCE,
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
