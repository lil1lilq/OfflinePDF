"""Check native diagnostic control flow; actual WFP checks run on Windows CI."""

import ctypes
from unittest import TestCase
from unittest.mock import Mock, patch

from offline_pdf.diagnostics import native_tcp_probe


class NativeProbeTests(TestCase):
    def library(self, connect_error):
        api = Mock()
        api.WSAStartup.return_value = 0
        api.socket.return_value = 123
        api.ioctlsocket.return_value = 0
        api.connect.return_value = 0 if connect_error == 0 else -1
        api.WSAGetLastError.return_value = connect_error
        return api

    def test_immediate_connection_and_native_denial(self):
        for error, connected in [(0, True), (10013, False)]:
            api = self.library(error)
            with patch("ctypes.WinDLL", return_value=api, create=True):
                result = native_tcp_probe()
            self.assertEqual(result, {"connected": connected, "error": error})
            api.closesocket.assert_called_once_with(123)
            api.WSACleanup.assert_called_once()

    def test_nonblocking_success_and_timeout_are_distinct(self):
        for ready in (0, 1):
            api = self.library(10035)
            api.select.return_value = ready

            def complete(handle, level, option, error, size):
                ctypes.cast(error, ctypes.POINTER(ctypes.c_int))[0] = 0
                return 0

            api.getsockopt.side_effect = complete
            with patch("ctypes.WinDLL", return_value=api, create=True):
                result = native_tcp_probe()
            self.assertEqual(result["connected"], ready == 1)
            self.assertEqual(result["error"], 0 if ready else 10060)
