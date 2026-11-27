import hashlib
import io
import json
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from offline_pdf import sign_update, update_service
from offline_pdf.update_service import (
    MANIFEST,
    SETUP,
    SIGNATURE,
    UpdateError,
    download,
    release_info,
    signed_installer_hash,
    validate_url,
    version_tuple,
    worker,
)


def signed_release(payload, tag="v1.3.2", **overrides):
    key = Ed25519PrivateKey.generate()
    record = {
        "schema": 1,
        "project": "lil1lilq/OfflinePDF",
        "tag": tag,
        "asset": SETUP,
        "sha256": hashlib.sha256(payload).hexdigest(),
        **overrides,
    }
    manifest = json.dumps(record).encode()
    public_key = key.public_key().public_bytes_raw().hex()
    return public_key, {"manifest": manifest, "signature": key.sign(manifest)}


def socket_probe(events):
    import socket

    with socket.socket():
        events.put(True)


class UpdateServiceTests(unittest.TestCase):
    def test_gui_import_after_network_guard_in_fresh_interpreter(self):
        # Full test discovery can preload ssl and hide frozen-app startup errors.
        script = (
            "from offline_pdf.engine import disable_network; "
            "disable_network(); "
            "from offline_pdf import updates; "
            "import socket; "
            "assert socket.socket.__name__ == 'denied'"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_network_capable_child_does_not_enable_parent_network(self):
        import socket

        ctx = mp.get_context("spawn")
        events = ctx.Queue()
        process = ctx.Process(target=socket_probe, args=(events,))
        try:
            with patch.object(socket, "socket", side_effect=PermissionError("disabled")):
                process.start()
                self.assertTrue(events.get(timeout=15))
                with self.assertRaises(PermissionError):
                    socket.socket()
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            events.close()

    @unittest.skipUnless(os.name == "nt", "Windows registry required")
    def test_installed_location_matches_executable_directory(self):
        import winreg

        from offline_pdf import updates

        key = "Software\\OfflinePDF-update-test-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as temporary:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
                winreg.SetValueEx(handle, "InstallLocation", 0, winreg.REG_SZ, temporary)
            try:
                with (
                    patch.object(updates, "UNINSTALL", key),
                    patch("sys.frozen", True, create=True),
                    patch("sys.executable", str(Path(temporary) / "OfflinePDF.exe")),
                ):
                    self.assertEqual(
                        updates.installed_location(), (Path(temporary).resolve(), "/CURRENTUSER")
                    )
                with (
                    patch.object(updates, "UNINSTALL", key),
                    patch("sys.frozen", True, create=True),
                    patch("sys.executable", str(Path(temporary) / "portable" / "OfflinePDF.exe")),
                ):
                    self.assertIsNone(updates.installed_location())
            finally:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)

    def test_release_comparison_and_official_urls(self):
        release = {"tag_name": "v1.2.3.1", "assets": [{"name": SETUP}, {"name": "SHA256SUMS.txt"}]}
        with patch.object(update_service, "TRUSTED_PUBLIC_KEYS", ("test-key",)):
            self.assertFalse(release_info(release, "1.2.3")["installable"])
            release["assets"].extend([{"name": MANIFEST}, {"name": SIGNATURE}])
            info = release_info(release, "1.2.3")
        with patch.object(update_service, "TRUSTED_PUBLIC_KEYS", ()):
            self.assertFalse(release_info(release, "1.2.3")["installable"])
        self.assertTrue(info["available"])
        self.assertTrue(info["installable"])
        self.assertFalse(release_info({"tag_name": "v1.2.3"}, "1.2.4")["available"])
        for value in ("../../bad", "v1.2.3-beta", "https://evil.invalid", "1.2"):
            with self.assertRaises(UpdateError):
                version_tuple(value)
        for url in (
            "http://github.com/test",
            "https://github.com.evil.invalid/test",
            "https://user:secret@github.com/test",
            "file:///tmp/setup.exe",
        ):
            with self.assertRaises(UpdateError):
                validate_url(url)
        with self.assertRaises(UpdateError):
            release_info({"tag_name": "v1.3.0", "prerelease": True}, "1.2.3")

    def test_download_verifies_hash_and_rolls_back_partial_files(self):
        payload = b"synthetic installer, never executed"
        key, signed = signed_release(payload)

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(update_service, "TRUSTED_PUBLIC_KEYS", (key,)),
            patch.object(update_service, "read_small", side_effect=list(signed.values()) * 3),
            patch.object(
                update_service, "open_url", side_effect=[Response(payload), Response(b"changed")]
            ) as open_url,
        ):
            result = download("v1.3.2", "1.3.1", temporary, Mock())
            self.assertEqual(Path(temporary, SETUP).read_bytes(), payload)
            self.assertEqual(result["signature"], signed["signature"])
            Path(temporary, SETUP).unlink()
            with self.assertRaises(UpdateError):
                download("v1.3.2", "1.3.1", temporary, Mock())
            self.assertEqual(list(Path(temporary).iterdir()), [])
            with self.assertRaises(UpdateError):
                download("v1.3.3", "1.3.1", temporary, Mock())
            self.assertEqual(open_url.call_count, 2)

    def test_signed_manifest_rejects_mismatch_and_rollback(self):
        key, signed = signed_release(b"installer")
        manifest, signature = signed.values()
        for bad_manifest, bad_signature, tag, current in (
            (manifest + b" ", signature, "v1.3.2", "1.3.1"),
            (manifest, b"0" * 64, "v1.3.2", "1.3.1"),
            (manifest, signature, "v1.3.3", "1.3.1"),
            (manifest, signature, "v1.3.2", "1.3.2"),
        ):
            with patch.object(update_service, "TRUSTED_PUBLIC_KEYS", (key,)):
                with self.assertRaises(UpdateError):
                    signed_installer_hash(bad_manifest, bad_signature, tag, current)
        for override in ({"asset": "other.exe"}, {"project": "other"}, {"sha256": "invalid"}):
            wrong_key, wrong = signed_release(b"installer", **override)
            with patch.object(update_service, "TRUSTED_PUBLIC_KEYS", (wrong_key,)):
                with self.assertRaises(UpdateError):
                    signed_installer_hash(*wrong.values(), "v1.3.2", "1.3.1")
        with patch.object(update_service, "TRUSTED_PUBLIC_KEYS", ("00" * 32,)):
            with self.assertRaises(UpdateError):
                signed_installer_hash(manifest, signature, "v1.3.2", "1.3.1")

    def test_release_signing_tool_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            installer = Path(temporary, SETUP)
            installer.write_bytes(b"installer")
            private_key = Path(temporary, "test.pem")
            with (
                patch.object(sign_update.getpass, "getpass", return_value="test-passphrase"),
                patch("builtins.print") as output,
            ):
                sign_update.generate_key(private_key)
                self.assertIn(b"BEGIN ENCRYPTED PRIVATE KEY", private_key.read_bytes())
                key = output.call_args.args[0]
                with patch.object(sign_update, "TRUSTED_PUBLIC_KEYS", (key,)):
                    sign_update.sign_release(installer, private_key)
            with patch.object(update_service, "TRUSTED_PUBLIC_KEYS", (key,)):
                result = signed_installer_hash(
                    Path(temporary, MANIFEST).read_bytes(),
                    Path(temporary, SIGNATURE).read_bytes(),
                    "v" + sign_update.__version__,
                    "0.0.0",
                )
            self.assertEqual(result, hashlib.sha256(b"installer").hexdigest())

    def test_worker_emits_no_document_details_on_network_failure(self):
        events = Mock()
        with patch("offline_pdf.update_service.read_small", side_effect=OSError("SECRET PATH")):
            worker("check", "1.2.3", events)
        self.assertEqual(events.put.call_args.args[0]["type"], "error")
        self.assertNotIn("SECRET PATH", str(events.put.call_args))
        with patch(
            "offline_pdf.update_service.read_small",
            return_value=json.dumps({"tag_name": "v1.2.4"}).encode(),
        ):
            worker("check", "1.2.3", events)
        self.assertTrue(events.put.call_args.args[0]["available"])


class UpdateGuiTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk

        try:
            self.root = ctk.CTk()
        except Exception:
            self.skipTest("Desktop unavailable")
        from offline_pdf.updates import UpdateDialog

        self.app = SimpleNamespace(root=self.root, busy=Mock(return_value=False), close=Mock())
        with patch.object(UpdateDialog, "launch") as launch:
            self.window = UpdateDialog(self.app)
            launch.assert_called_once_with("check")
        self.root.update()

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
            for timer in self.root.tk.call("after", "info"):
                self.root.after_cancel(timer)
            self.root.destroy()

    def test_busy_job_blocks_installer_then_requires_verified_file(self):
        from offline_pdf.updates import installed_location

        self.assertIsNone(installed_location())
        self.app.busy.return_value = True
        key, self.window.downloaded = signed_release(b"missing")
        self.window.release = {"tag": "v1.3.2"}
        with patch("offline_pdf.updates.subprocess.Popen") as popen:
            self.window.install()
            popen.assert_not_called()
        self.app.busy.return_value = False
        with (
            patch(
                "offline_pdf.updates.installed_location",
                return_value=(Path("C:/OfflinePDF"), "/CURRENTUSER"),
            ),
            patch("offline_pdf.updates.messagebox.askokcancel", return_value=True),
            patch.object(update_service, "TRUSTED_PUBLIC_KEYS", (key,)),
            patch("offline_pdf.updates.subprocess.Popen") as popen,
        ):
            self.window.install()
            popen.assert_not_called()
            self.app.close.assert_not_called()

    def test_valid_installer_launch_and_close_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / SETUP
            path.write_bytes(b"test")
            key, self.window.downloaded = signed_release(b"test")
            self.window.release = {"tag": "v1.3.2"}
            self.window.folder = temporary
            with (
                patch(
                    "offline_pdf.updates.installed_location",
                    return_value=(Path("C:/OfflinePDF"), "/CURRENTUSER"),
                ),
                patch("offline_pdf.updates.messagebox.askokcancel", return_value=True),
                patch.object(update_service, "TRUSTED_PUBLIC_KEYS", (key,)),
                patch("offline_pdf.updates.subprocess.Popen") as popen,
            ):
                path.write_bytes(b"changed after download")
                self.window.install()
                popen.assert_not_called()
                path.write_bytes(b"test")
                self.window.install()
                self.assertIn("/CURRENTUSER", popen.call_args.args[0])
                self.app.close.assert_called_once()
                self.assertTrue(self.app._installing)
