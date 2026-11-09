"""Tests for web.reject_log (stdlib only — no FastAPI needed)."""

import os
import tempfile
import unittest

from web.reject_log import MAX_LOG_BYTES, append_reject, log_path, reject_line


class RejectLogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("API_REJECT_LOG")
        os.environ["API_REJECT_LOG"] = os.path.join(self._tmp.name, "api_reject.log")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("API_REJECT_LOG", None)
        else:
            os.environ["API_REJECT_LOG"] = self._prev
        self._tmp.cleanup()

    def test_line_shape(self):
        line = reject_line("POST", "/api/days/20261109/items", 422, b'{"weight": "150"}')
        self.assertIn("[api-reject] POST /api/days/20261109/items -> 422", line)
        self.assertIn('body: {"weight": "150"}', line)
        self.assertTrue(line.endswith("\n"))

    def test_appends_and_creates_dir(self):
        append_reject("POST", "/api/foods", 409, b"{}")
        append_reject("POST", "/api/foods", 409, b"{}")
        text = log_path().read_text(encoding="utf-8")
        self.assertEqual(text.count("[api-reject]"), 2)

    def test_invalid_utf8_body_no_crash(self):
        append_reject("POST", "/api/foods", 422, b"\xff\xfe bad")
        self.assertIn("bad", log_path().read_text(encoding="utf-8"))

    def test_body_truncated(self):
        append_reject("POST", "/api/foods", 422, b"x" * 5000)
        for line in log_path().read_text(encoding="utf-8").splitlines():
            if "body:" in line:
                self.assertLessEqual(len(line), 810)

    def test_rotation_cap(self):
        log_path().write_bytes(b"a" * (MAX_LOG_BYTES + 10))
        append_reject("POST", "/api/foods", 422, b"small")
        text = log_path().read_text(encoding="utf-8")
        self.assertIn("rotated", text)
        self.assertLess(len(text.encode()), MAX_LOG_BYTES)

    def test_default_path_is_repo_data(self):
        os.environ.pop("API_REJECT_LOG", None)
        try:
            self.assertEqual(log_path().name, "api_reject.log")
            self.assertEqual(log_path().parent.name, "data")
        finally:
            os.environ["API_REJECT_LOG"] = os.path.join(self._tmp.name, "api_reject.log")


if __name__ == "__main__":
    unittest.main()
