"""Explicit, isolated update requests. Receives no document data or passwords."""

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

API = "https://api.github.com/repos/lil1lilq/OfflinePDF/releases/latest"
RELEASES = "https://github.com/lil1lilq/OfflinePDF/releases"
SETUP = "OfflinePDF-Setup-Windows-x64.exe"
HOSTS = {
    "api.github.com",
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
}
LIMIT = 512 * 1024 * 1024


class UpdateError(Exception):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:\.\d+)?", value):
        raise UpdateError("릴리즈 버전 형식을 확인할 수 없습니다.")
    parts = tuple(int(x) for x in value.removeprefix("v").split("."))
    return parts + (0,) * (4 - len(parts))


def release_info(data, current):
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise UpdateError("정식 릴리즈 정보를 확인할 수 없습니다.")
    tag = data.get("tag_name")
    available = version_tuple(tag) > version_tuple(current)
    names = {a.get("name") for a in data.get("assets", []) if isinstance(a, dict)}
    return {
        "version": tag.removeprefix("v"),
        "tag": tag,
        "available": available,
        "installable": SETUP in names and "SHA256SUMS.txt" in names,
        "url": RELEASES + "/tag/" + tag,
    }


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.username
        or parsed.password
    ):
        raise UpdateError("공식 다운로드 주소를 확인할 수 없습니다.")


def open_url(url):
    # The GUI replaces socket.socket to block document-process networking.
    # Importing ssl after that replacement cannot define SSLSocket. Only the
    # fresh update worker may load HTTP/TLS modules, never GUI initialization.
    import urllib.request

    class TrustedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, newurl):
            validate_url(newurl)
            return super().redirect_request(request, fp, code, message, headers, newurl)

    validate_url(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": "OfflinePDF-Update", "Accept": "application/vnd.github+json"}
    )
    return urllib.request.build_opener(TrustedRedirect()).open(request, timeout=15)


def read_small(url):
    with open_url(url) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise UpdateError("업데이트 정보가 너무 큽니다.")
    return data


def expected_hash(data):
    matches = []
    for line in data.decode("utf-8-sig").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+\*?" + re.escape(SETUP), line.strip())
        if match:
            matches.append(match[1].lower())
    if len(matches) != 1:
        raise UpdateError("설치파일 검증 정보를 확인할 수 없습니다.")
    return matches[0]


def verify_file(path, expected):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise UpdateError("설치파일 검증에 실패했습니다. 다운로드를 다시 시도하세요.")


def download(tag, folder, emit):
    version_tuple(tag)
    base = RELEASES + "/download/" + tag + "/"
    expected = expected_hash(read_small(base + "SHA256SUMS.txt"))
    target = Path(folder) / SETUP
    partial = target.with_suffix(".partial")
    count, started = 0, time.monotonic()
    try:
        with open_url(base + SETUP) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            if total > LIMIT:
                raise UpdateError("설치파일이 너무 큽니다.")
            while True:
                block = response.read(256 * 1024)
                if not block:
                    break
                count += len(block)
                if count > LIMIT or time.monotonic() - started > 300:
                    raise UpdateError("다운로드 제한을 초과했습니다. 나중에 다시 시도하세요.")
                output.write(block)
                emit({"type": "progress", "current": count, "total": total})
        verify_file(partial, expected)
        partial.replace(target)
        return {"type": "downloaded", "path": str(target), "sha256": expected}
    finally:
        partial.unlink(missing_ok=True)


def worker(action, current, events, tag=None, folder=None):
    """Spawned with a fresh interpreter, outside engine.disable_network()."""
    try:
        if action == "check":
            result = release_info(json.loads(read_small(API)), current)
            events.put({"type": "release", **result})
        elif action == "download":
            events.put(download(tag, folder, events.put))
        else:
            raise UpdateError("업데이트 요청을 확인하세요.")
    except Exception as exc:
        events.put(
            {
                "type": "error",
                "message": str(exc)
                if isinstance(exc, UpdateError)
                else "업데이트를 확인하지 못했습니다. 인터넷 연결 또는 사내 네트워크 정책을 확인하세요.",
            }
        )
