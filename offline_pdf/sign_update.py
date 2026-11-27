"""Generate a release key and sign updates on the release maintainer's computer."""

import argparse
import getpass
import json
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import __version__
from .update_keys import TRUSTED_PUBLIC_KEYS
from .update_service import (
    LIMIT,
    MANIFEST,
    SETUP,
    SIGNATURE,
    UPDATE_PROJECT,
    UPDATE_SCHEMA,
    file_sha256,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def generate_key(path):
    if path.is_relative_to(SOURCE_ROOT):
        raise ValueError("개인 키 저장 위치는 OfflinePDF 소스 폴더 밖이어야 합니다.")
    password = getpass.getpass("개인 키 보호 암호: ")
    if not password or password != getpass.getpass("암호 확인: "):
        raise ValueError("보호 암호를 입력하고 동일하게 확인해 주세요.")
    key = Ed25519PrivateKey.generate()
    encrypted = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as output:
        output.write(encrypted)
    print("공개 키 (offline_pdf/update_keys.py의 TRUSTED_PUBLIC_KEYS에 추가):")
    print(key.public_key().public_bytes_raw().hex())


def sign_release(installer, key_path):
    if installer.name != SETUP or not 0 < installer.stat().st_size <= LIMIT:
        raise ValueError(f"배포용 설치파일 {SETUP}을 선택하세요.")
    password = getpass.getpass("개인 키 보호 암호: ").encode("utf-8")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=password)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 개인 키가 필요합니다.")
    if key.public_key().public_bytes_raw().hex() not in TRUSTED_PUBLIC_KEYS:
        raise ValueError("개인 키와 맞는 공개 키를 TRUSTED_PUBLIC_KEYS에 먼저 등록하세요.")

    record = {
        "schema": UPDATE_SCHEMA,
        "project": UPDATE_PROJECT,
        "tag": "v" + __version__,
        "asset": SETUP,
        "sha256": file_sha256(installer),
    }
    manifest = (json.dumps(record, indent=2) + "\n").encode("utf-8")
    signature = key.sign(manifest)
    with tempfile.TemporaryDirectory(dir=installer.parent) as temporary:
        stage = Path(temporary)
        (stage / MANIFEST).write_bytes(manifest)
        (stage / SIGNATURE).write_bytes(signature)
        (stage / MANIFEST).replace(installer.parent / MANIFEST)
        (stage / SIGNATURE).replace(installer.parent / SIGNATURE)
    print(f"{record['tag']}: {MANIFEST}, {SIGNATURE} 생성 완료")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="암호로 보호된 개인 키 만들기")
    keygen.add_argument("key", type=Path)
    sign = commands.add_parser("sign", help="현재 소스 버전의 설치파일 서명")
    sign.add_argument("installer", type=Path)
    sign.add_argument("key", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            generate_key(args.key.expanduser().resolve())
        else:
            sign_release(args.installer.resolve(), args.key.expanduser().resolve())
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
