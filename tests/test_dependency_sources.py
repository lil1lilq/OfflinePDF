"""Downloading AGPL dependency sources survives temporary server errors."""

import importlib.util
import urllib.error
from pathlib import Path
from unittest import TestCase

_spec = importlib.util.spec_from_file_location(
    "prepare_dependency_sources",
    Path(__file__).resolve().parents[1] / "packaging" / "prepare_dependency_sources.py",
)
sources = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sources)


def http_error(code):
    return urllib.error.HTTPError("https://example.invalid", code, "error", {}, None)


class RetryTests(TestCase):
    def run_with(self, failures):
        calls, waits = [], []

        def action():
            calls.append(1)
            if failures:
                raise failures.pop(0)
            return "done"

        result = sources.retrying(action, "https://example.invalid", sleep=waits.append)
        return result, len(calls), waits

    def test_gateway_timeouts_are_retried(self):
        # Build #29 failed on one 504 from the MuPDF download server.
        result, calls, waits = self.run_with([http_error(504), http_error(503)])
        self.assertEqual((result, calls), ("done", 3))
        self.assertEqual(waits, list(sources.RETRY_DELAYS[:2]))

    def test_connection_problems_are_retried(self):
        result, calls, _ = self.run_with([urllib.error.URLError("reset"), TimeoutError()])
        self.assertEqual((result, calls), ("done", 3))

    def test_missing_file_fails_at_once(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.run_with([http_error(404)])

    def test_gives_up_after_the_last_retry(self):
        failures = [http_error(504) for _ in range(len(sources.RETRY_DELAYS) + 1)]
        with self.assertRaises(urllib.error.HTTPError):
            self.run_with(failures)
