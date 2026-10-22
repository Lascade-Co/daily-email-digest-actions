"""Workflow lint for the delivery guarantees that execute on GitHub runners."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.reusable = workflow("_digest.yml")
        self.email = self.reusable["jobs"]["email"]

    def test_lock_covers_build_hold_dedupe_and_final_send_across_events(self):
        group = self.email["concurrency"]["group"]
        self.assertEqual(group, "digest-${{ inputs.workflow }}-${{ matrix.digest }}-${{ inputs.edition }}")
        self.assertEqual(self.email["concurrency"]["cancel-in-progress"], "false")
        self.assertGreaterEqual(int(self.email["timeout-minutes"]), 75)
        steps = self.email["steps"]
        build = next(i for i, step in enumerate(steps) if step.get("name") == "Build email")
        hold = next(i for i, step in enumerate(steps) if "hold.py" in step.get("run", ""))
        dedupe = next(i for i, step in enumerate(steps) if step.get("id") == "dedupe")
        self.assertLess(build, hold)
        self.assertEqual(hold + 1, dedupe)
        self.assertEqual(steps[hold]["if"], "${{ github.event_name == 'schedule' }}")
        self.assertIn("smtp_send.py", steps[-1]["run"])
        self.assertEqual(steps[-1]["name"], "${{ steps.settings.outputs.send_step }}")
        self.assertEqual(steps[-1]["if"], "${{ !inputs.dry_run }}")

    def test_partial_matrix_dry_and_test_cannot_emit_aggregate_delivery_marker(self):
        done = self.reusable["jobs"]["done"]
        self.assertEqual(done["needs"], "email")
        self.assertEqual(done["if"], "${{ !inputs.dry_run && inputs.to == '' && needs.email.result == 'success' }}")
        self.assertEqual(self.email["strategy"]["fail-fast"], "false")
        self.assertNotIn("continue-on-error", self.email)
        for step in self.email["steps"]:
            self.assertNotIn("continue-on-error", step)

    def test_aggregate_delivery_marker_uses_the_callers_frozen_report_day(self):
        done = self.reusable["jobs"]["done"]
        self.assertEqual(done["steps"][0]["name"],
                         "Delivered ${{ inputs.edition == 'pt' && 'PT' || 'IST' }} for ${{ inputs.report_date }}")
        self.assertNotIn("report_date", self.email.get("outputs", {}))
        self.assertEqual(self.reusable["env"]["REPORT_DATE"], "${{ inputs.report_date }}")

    def test_callers_dispatch_same_branch_and_manual_both_fans_out(self):
        for name, pt, ist in [("revenue",45,11), ("reviews",47,13), ("survey",49,15), ("conversion",51,17)]:
            with self.subTest(name=name):
                caller = workflow(f"daily-{name}.yml")
                self.assertEqual([s["cron"] for s in caller["on"]["schedule"]],
                                 [f"{pt} 3,6,9 * * *", f"{ist} 13,16,19 * * *"])
                job = caller["jobs"]["email"]
                self.assertEqual(job["uses"], "./.github/workflows/_digest.yml")
                self.assertEqual(job["strategy"]["matrix"],
                                 {"include": "${{ fromJSON(needs.gate2.outputs.editions) }}"})
                self.assertEqual(job["with"]["edition"], "${{ matrix.edition }}")
                self.assertEqual(job["with"]["report_date"], "${{ matrix.report_date }}")
                self.assertEqual(caller["jobs"]["gate"]["outputs"]["editions"],
                                 "${{ steps.settings.outputs.editions }}")
                self.assertEqual(caller["jobs"]["gate2"]["outputs"]["editions"],
                                 "${{ needs.gate.outputs.editions }}")
                self.assertEqual(job["secrets"], "inherit")
                self.assertEqual(set(caller["jobs"]), {"gate", "gate2", "email"})
        checkout = next(s for s in self.email["steps"] if s.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")

    def test_settings_can_query_the_current_runs_creation_time(self):
        self.assertEqual(self.reusable["env"].get("GH_TOKEN"), "${{ github.token }}")
        for name in ["revenue", "reviews", "survey", "conversion"]:
            with self.subTest(name=name):
                caller = workflow(f"daily-{name}.yml")
                settings = next(step for step in caller["jobs"]["gate"]["steps"]
                                if step.get("id") == "settings")
                self.assertEqual(settings.get("env", {}).get("GH_TOKEN"), "${{ github.token }}")

    def test_timing_gates_use_the_report_day_frozen_before_sleep(self):
        for name in ["revenue", "reviews", "survey", "conversion"]:
            with self.subTest(name=name):
                jobs = workflow(f"daily-{name}.yml")["jobs"]
                self.assertEqual(jobs["gate"]["outputs"]["report_date"],
                                 "${{ steps.settings.outputs.report_date }}")
                first = next(step for step in jobs["gate"]["steps"] if step.get("id") == "timing")
                self.assertEqual(first["env"].get("REPORT_DATE"), "${{ steps.settings.outputs.report_date }}")
                self.assertIn('--report-date "$REPORT_DATE"', first["run"])
                second = jobs["gate2"]["steps"][0]
                self.assertEqual(second["env"]["REPORT_DATE"], "${{ needs.gate.outputs.report_date }}")
                self.assertIn('--report-date "$REPORT_DATE"', second["run"])

    def test_public_artifact_is_only_encrypted_archive(self):
        uploads = [s for s in self.email["steps"] if s.get("uses", "").startswith("actions/upload-artifact@")]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]["if"], "${{ inputs.dry_run }}")
        self.assertEqual(uploads[0]["with"]["path"], "preview.tar.gz.enc")
        self.assertEqual(uploads[0]["with"]["name"], "preview-${{ matrix.digest }}-${{ inputs.edition }}")

    @unittest.skipUnless(shutil.which("openssl"), "openssl is required for preview encryption")
    def test_encryption_step_round_trips_only_preview_files(self):
        encrypt = next(s for s in self.email["steps"] if s.get("name") == "Encrypt preview")
        scratch = ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            base = Path(directory)
            (base / "out").mkdir()
            (base / "out/revenue-pt.html").write_text("<html>Private fixture</html>")
            (base / "out/revenue-pt.subject.txt").write_text("Private fixture subject")
            # GitHub uses GNU tar on Ubuntu; macOS otherwise adds AppleDouble
            # resource forks unrelated to the preview file contract.
            env = {**os.environ, "PREVIEW_KEY": "offline-fixture-key", "COPYFILE_DISABLE": "1"}
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", encrypt["run"]],
                                    cwd=base, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(b"Private fixture", result.stdout + result.stderr)
            archive = (base / "preview.tar.gz.enc").read_bytes()
            self.assertNotIn(b"Private fixture", archive)
            plain = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                                    "-pass", "env:PREVIEW_KEY"], input=archive, env=env, capture_output=True)
            self.assertEqual(plain.returncode, 0, plain.stderr)
            with tarfile.open(fileobj=io.BytesIO(plain.stdout), mode="r:gz") as tar:
                files = sorted(m.name for m in tar.getmembers() if m.isfile())
            self.assertEqual(files, ["out/revenue-pt.html", "out/revenue-pt.subject.txt"])

    def test_recipient_input_is_not_exposed_in_actions_environment_headers(self):
        for name in ["_digest.yml", "daily-revenue.yml", "daily-reviews.yml", "daily-survey.yml", "daily-conversion.yml"]:
            document = workflow(name)
            envs = [document.get("env", {})]
            for job in document["jobs"].values():
                envs.append(job.get("env", {}))
                envs.extend(step.get("env", {}) for step in job.get("steps", []))
            for env in envs:
                self.assertNotIn("${{ inputs.to }}", env.values())


if __name__ == "__main__":
    unittest.main()
