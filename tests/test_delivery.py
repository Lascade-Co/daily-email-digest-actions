"""Resend delivery payload, frozen-envelope, and public-log safety tests."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


@contextlib.contextmanager
def _chdir(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


class DeliveryTests(unittest.TestCase):
    def _module(self):
        self.assertIsNotNone(importlib.util.find_spec("scripts.common.delivery"),
                             "shared Resend delivery has not been implemented")
        from scripts.common import delivery
        return delivery

    def test_transport_encodes_subject_and_test_recipient_without_logging_content(self):
        delivery = self._module()
        config = {"digests": {"revenue": {"sender": "MarineRadar", "recipients": {
            "pt": ["production@example.com"], "ist": ["team@example.com"]}}}}
        subject = "MarineRadar web revenue · Tue, Oct 21 — $412 (3 purchases)"
        output = io.StringIO()
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory, \
             _chdir(directory), \
             patch.dict(os.environ, {"RESEND_API_KEY": "re_test_key", "MAIL_FROM": "noreply@lascade.com",
                                     "GITHUB_RUN_ID": "42", "GITHUB_ACTIONS": "false"}), \
             patch.object(delivery, "requests", mock_session), \
             contextlib.redirect_stdout(output):
            delivery.send_digest("revenue", "pt", subject, "<p>private body</p>",
                                 test_to="test@example.com", config=config,
                                 report_date="2026-10-21")

        mock_session.post.assert_called_once()
        call_kwargs = mock_session.post.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[0][1]
        self.assertIn("Bearer re_test_key", headers["Authorization"])
        self.assertIn("Idempotency-Key", headers)
        payload = json.loads(call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs[0][2])
        self.assertEqual(payload["to"], ["test@example.com"])
        self.assertEqual(payload["subject"], "[TEST] " + subject)
        self.assertIn("MarineRadar", payload["from"])
        self.assertEqual(payload["html"], "<p>private body</p>")

        log = output.getvalue()
        for private in (subject, "private body", "production@example.com",
                        "test@example.com", "noreply@lascade.com", "re_test_key"):
            self.assertNotIn(private, log)
        self.assertIn(hashlib.sha256(("[TEST] " + subject).encode()).hexdigest()[:8], log)

    def test_preview_files_are_utf8_with_no_raw_subject_log(self):
        delivery = self._module()
        output = io.StringIO()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory, \
             contextlib.redirect_stdout(output):
            delivery.write_preview("conversion", "ist",
                                   "Install → Paid · Wed, Oct 21 — 14 days",
                                   "<html>private body</html>", out_dir=directory)
            files = sorted(p.name for p in Path(directory).iterdir())
            self.assertEqual(files, ["conversion-ist.html", "conversion-ist.subject.txt"])
            self.assertEqual((Path(directory) / "conversion-ist.subject.txt").read_text(),
                             "Install → Paid · Wed, Oct 21 — 14 days")
        self.assertNotIn("private body", output.getvalue())
        self.assertNotIn("Install → Paid", output.getvalue())

    def test_resend_api_error_does_not_expose_response_body(self):
        delivery = self._module()
        config = {"digests": {"revenue": {"sender": "MarineRadar", "recipients": {
            "pt": ["private@example.com"]}}}}
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_session.post.return_value = mock_response

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory, \
             _chdir(directory), \
             patch.dict(os.environ, {"RESEND_API_KEY": "re_test_key", "MAIL_FROM": "noreply@lascade.com",
                                     "GITHUB_ACTIONS": "false"}), \
             patch.object(delivery, "requests", mock_session):
            with self.assertRaisesRegex(delivery.DeliveryError, "Resend delivery failed") as result:
                delivery.send_digest("revenue", "pt", "private subject", "private body",
                                     config=config, report_date="2026-10-21")
        self.assertNotIn("private@example.com", str(result.exception))
        self.assertNotIn("private subject", str(result.exception))

    def test_retry_on_429_then_success(self):
        delivery = self._module()
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        mock_session = MagicMock()
        response_429 = MagicMock()
        response_429.status_code = 429
        response_200 = MagicMock()
        response_200.status_code = 200
        mock_session.post.side_effect = [response_429, response_200]

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "envelope.json")
            delivery.freeze_envelope(path, "test/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            result = delivery.send_frozen(path, "re_key", session=mock_session, sleep_fn=fake_sleep)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(mock_session.post.call_count, 2)
        self.assertEqual(len(sleeps), 1)

    def test_retry_on_5xx_then_success(self):
        delivery = self._module()
        mock_session = MagicMock()
        response_500 = MagicMock()
        response_500.status_code = 500
        response_200 = MagicMock()
        response_200.status_code = 200
        mock_session.post.side_effect = [response_500, response_200]

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "envelope.json")
            delivery.freeze_envelope(path, "test/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            result = delivery.send_frozen(path, "re_key", session=mock_session, sleep_fn=lambda _: None)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["attempts"], 2)

    def test_409_concurrent_retries_then_succeeds(self):
        delivery = self._module()
        mock_session = MagicMock()
        response_409 = MagicMock()
        response_409.status_code = 409
        response_409.json.return_value = {"name": "concurrent_idempotent_requests"}
        response_200 = MagicMock()
        response_200.status_code = 200
        mock_session.post.side_effect = [response_409, response_200]

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "envelope.json")
            delivery.freeze_envelope(path, "test/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            result = delivery.send_frozen(path, "re_key", session=mock_session, sleep_fn=lambda _: None)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["attempts"], 2)

    def test_409_payload_mismatch_fails_immediately(self):
        delivery = self._module()
        mock_session = MagicMock()
        response_409 = MagicMock()
        response_409.status_code = 409
        response_409.json.return_value = {"name": "invalid_idempotent_request"}
        mock_session.post.return_value = response_409

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "envelope.json")
            delivery.freeze_envelope(path, "test/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            with self.assertRaisesRegex(delivery.DeliveryError, "invalid_idempotent_request"):
                delivery.send_frozen(path, "re_key", session=mock_session, sleep_fn=lambda _: None)
        self.assertEqual(mock_session.post.call_count, 1)

    def test_max_attempts_exhausted(self):
        delivery = self._module()
        mock_session = MagicMock()
        response_500 = MagicMock()
        response_500.status_code = 500
        mock_session.post.return_value = response_500

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "envelope.json")
            delivery.freeze_envelope(path, "test/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            with self.assertRaisesRegex(delivery.DeliveryError, "Resend delivery failed"):
                delivery.send_frozen(path, "re_key", max_attempts=3,
                                     session=mock_session, sleep_fn=lambda _: None)
        self.assertEqual(mock_session.post.call_count, 3)

    def test_freeze_envelope_creates_private_file(self):
        delivery = self._module()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "frozen.json")
            delivery.freeze_envelope(path, "my/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            self.assertTrue(os.path.exists(path))
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(mode, 0o600)
            with open(path) as f:
                envelope = json.load(f)
            self.assertEqual(envelope["key"], "my/key")
            payload = json.loads(envelope["body"])
            self.assertEqual(payload["subject"], "s")

    def test_freeze_envelope_fails_if_file_exists(self):
        delivery = self._module()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "frozen.json")
            delivery.freeze_envelope(path, "my/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            with self.assertRaisesRegex(delivery.DeliveryError, "already exists"):
                delivery.freeze_envelope(path, "my/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})

    def test_idempotency_key_production_format(self):
        delivery = self._module()
        key = delivery.idempotency_key("revenue", "pt", report_date="2026-10-21")
        self.assertEqual(key, "revenue/pt/2026-10-21")

    def test_idempotency_key_test_format(self):
        delivery = self._module()
        key = delivery.idempotency_key("revenue", "pt", test_to="x@y.com", run_id="123")
        self.assertEqual(key, "revenue/pt/test/123")

    def test_missing_api_key_raises(self):
        delivery = self._module()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "frozen.json")
            delivery.freeze_envelope(path, "test/key", {"from": "a", "to": ["b"], "subject": "s", "html": "h"})
            with self.assertRaisesRegex(delivery.DeliveryError, "API key is missing"):
                delivery.send_frozen(path, "")


if __name__ == "__main__":
    unittest.main()
