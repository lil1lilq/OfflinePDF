"""Explicit, isolated update requests. Receives no document data or passwords."""

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

from .update_keys import TRUSTED_PUBLIC_KEYS

API = "https://api.github.com/repos/lil1lilq/OfflinePDF/releases/latest"
RELEASES = "https://github.com/lil1lilq/OfflinePDF/releases"
SETUP = "OfflinePDF-Setup-Windows-x64.exe"
MANIFEST = "update.json"
SIGNATURE = "update.sig"
UPDATE_SCHEMA = 1
UPDATE_PROJECT = "lil1lilq/OfflinePDF"
MANIFEST_LIMIT = 4096
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
    if not isinstance(value, str) or not re.fullmatch(
        r"v?[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}(?:\.[0-9]{1,5})?", value
    ):
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
        "installable": bool(TRUSTED_PUBLIC_KEYS) and {SETUP, MANIFEST, SIGNATURE} <= names,
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


def read_small(url, limit=1_000_000):
    with open_url(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("업데이트 정보가 너무 큽니다.")
    return data


def signed_installer_hash(manifest, signature, tag, current):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not TRUSTED_PUBLIC_KEYS:
        raise UpdateError("업데이트 서명 검증 키가 설정되지 않았습니다.")
    if len(manifest) > MANIFEST_LIMIT or len(signature) != 64:
        raise UpdateError("업데이트 서명을 검증할 수 없습니다.")
    for key in TRUSTED_PUBLIC_KEYS:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(signature, manifest)
        except (InvalidSignature, ValueError):
            continue
        break
    else:
        raise UpdateError("업데이트 서명을 검증할 수 없습니다.")

    try:
        record = json.loads(manifest.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise UpdateError("서명된 업데이트 정보가 올바르지 않습니다.") from None
    if (
        not isinstance(record, dict)
        or type(record.get("schema")) is not int
        or record["schema"] != UPDATE_SCHEMA
        or record.get("project") != UPDATE_PROJECT
        or record.get("asset") != SETUP
        or record.get("tag") != tag
        or version_tuple(tag) <= version_tuple(current)
    ):
        raise UpdateError("서명된 업데이트 정보가 올바르지 않습니다.")
    expected = record.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError("서명된 업데이트 정보가 올바르지 않습니다.")
    return expected


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path, expected):
    if file_sha256(path) != expected:
        raise UpdateError("설치파일 검증에 실패했습니다. 다운로드를 다시 시도하세요.")


def download(tag, current, folder, emit):
    version_tuple(tag)
    base = RELEASES + "/download/" + tag + "/"
    manifest = read_small(base + MANIFEST, MANIFEST_LIMIT)
    signature = read_small(base + SIGNATURE, 64)
    expected = signed_installer_hash(manifest, signature, tag, current)
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
        return {"type": "downloaded", "manifest": manifest, "signature": signature}
    finally:
        partial.unlink(missing_ok=True)


def worker(action, current, events, tag=None, folder=None):
    """Spawned with a fresh interpreter, outside engine.disable_network()."""
    try:
        if action == "check":
            result = release_info(json.loads(read_small(API)), current)
            events.put({"type": "release", **result})
        elif action == "download":
            events.put(download(tag, current, folder, events.put))
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
