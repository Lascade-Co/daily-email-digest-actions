"""SMTP payload and public-log safety tests with a local fake transport."""
import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from email import policy
from email.parser import Parser


class SmtpTests(unittest.TestCase):
    def _module(self):
        self.assertIsNotNone(importlib.util.find_spec("scripts.common.smtp_send"),
                             "shared SMTP transport has not been implemented")
        from scripts.common import smtp_send
        return smtp_send

    def test_transport_encodes_subject_and_test_recipient_without_logging_content(self):
        smtp_send = self._module()
        sent = []
        class FakeSmtp:
            def __init__(self, host, port, timeout):
                self.host, self.port = host, port
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
            def starttls(self, **kwargs):
                pass
            def login(self, user, password):
                pass
            def sendmail(self, user, recipients, payload):
                sent.append((user, recipients, payload))
                return {}

        config = {"digests": {"revenue": {"sender": "MarineRadar", "recipients": {
            "pt": ["production@example.com"], "ist": ["team@example.com"]}}}}
        subject = "MarineRadar web revenue · Tue, Oct 21 — $412 (3 purchases)"
        output = io.StringIO()
        with patch.dict(os.environ, {"GMAIL_USER": "sender@example.com", "GMAIL_APP_PASSWORD": "secret-password", "GITHUB_ACTIONS": "false"}), patch.object(smtp_send.smtplib, "SMTP", FakeSmtp), contextlib.redirect_stdout(output):
            smtp_send.send_digest("revenue", "pt", subject, "<p>private body</p>",
                                  test_to="test@example.com", config=config)
        self.assertEqual(len(sent), 1)
        _, recipients, payload = sent[0]
        message = Parser(policy=policy.default).parsestr(payload)
        self.assertEqual(recipients, ["test@example.com"])
        self.assertEqual(message["Subject"], "[TEST] " + subject)
        self.assertEqual(message["From"].addresses[0].display_name, "MarineRadar")
        self.assertEqual(message.get_payload(0).get_content(), "<p>private body</p>")
        log = output.getvalue()
        for private in (subject, "private body", "production@example.com", "test@example.com", "sender@example.com", "secret-password"):
            self.assertNotIn(private, log)
        self.assertIn(hashlib.sha256(("[TEST] " + subject).encode()).hexdigest()[:8], log)

    def test_preview_files_are_utf8_with_no_raw_subject_log(self):
        smtp_send = self._module()
        output = io.StringIO()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory, contextlib.redirect_stdout(output):
            smtp_send.write_preview("conversion", "ist", "Install → Paid · Wed, Oct 21 — 14 days", "<html>private body</html>", out_dir=directory)
            files = sorted(p.name for p in Path(directory).iterdir())
            self.assertEqual(files, ["conversion-ist.html", "conversion-ist.subject.txt"])
            self.assertEqual((Path(directory) / "conversion-ist.subject.txt").read_text(), "Install → Paid · Wed, Oct 21 — 14 days")
        self.assertNotIn("private body", output.getvalue())
        self.assertNotIn("Install → Paid", output.getvalue())

    def test_smtp_exception_does_not_expose_recipient_or_server_body(self):
        smtp_send = self._module()
        config = {"digests": {"revenue": {"sender": "MarineRadar", "recipients": {"pt": ["private@example.com"]}}}}
        with patch.dict(os.environ, {"GMAIL_USER": "sender@example.com", "GMAIL_APP_PASSWORD": "password", "GITHUB_ACTIONS": "false"}), patch.object(smtp_send.smtplib, "SMTP", side_effect=RuntimeError("private@example.com server-private-body")):
            with self.assertRaisesRegex(RuntimeError, "SMTP delivery failed") as result:
                smtp_send.send_digest("revenue", "pt", "private subject", "private body", config=config)
        self.assertNotIn("private@example.com", str(result.exception))
        self.assertNotIn("server-private-body", str(result.exception))


if __name__ == "__main__":
    unittest.main()
