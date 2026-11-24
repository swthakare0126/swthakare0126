"""Unit tests for .github/scripts/update_profile.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import update_profile as up  # noqa: E402


SAMPLE_README = """# Header
<!-- START_SECTION:snake -->
placeholder
<!-- END_SECTION:snake -->
<!-- START_SECTION:stats -->
placeholder
<!-- END_SECTION:stats -->
<!-- START_SECTION:repos -->
placeholder
<!-- END_SECTION:repos -->
<!-- START_SECTION:activity -->
placeholder
<!-- END_SECTION:activity -->
"""


class UpdateProfileTests(unittest.TestCase):
    def test_validate_readme_markers_passes(self) -> None:
        self.assertEqual(up.validate_readme_markers(SAMPLE_README), [])

    def test_validate_readme_markers_detects_missing(self) -> None:
        broken = SAMPLE_README.replace("<!-- END_SECTION:stats -->", "")
        errors = up.validate_readme_markers(broken)
        self.assertEqual(len(errors), 1)
        self.assertIn("stats", errors[0])

    def test_replace_section_handles_backslashes(self) -> None:
        updated = up.replace_section(SAMPLE_README, "stats", r"value \1 \n literal")
        self.assertIn(r"value \1 \n literal", updated)

    def test_build_stats_section(self) -> None:
        user = {"public_repos": 12, "followers": 34}
        repos = [
            {"fork": False, "stargazers_count": 5, "language": "HCL"},
            {"fork": False, "stargazers_count": 3, "language": "Python"},
            {"fork": True, "stargazers_count": 99, "language": "Go"},
        ]
        synced = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
        out = up.build_stats_section(user, repos, synced)
        self.assertIn("**12**", out)
        self.assertIn("**8**", out)
        self.assertIn("**34**", out)
        self.assertIn("HCL, Python", out)
        self.assertNotIn("Go", out)

    def test_build_repos_section_filters_profile_and_forks(self) -> None:
        repos = [
            {
                "name": "swthakare0126",
                "full_name": "swthakare0126/swthakare0126",
                "html_url": "https://github.com/swthakare0126/swthakare0126",
                "fork": False,
                "archived": False,
                "stargazers_count": 10,
                "pushed_at": "2026-11-24T00:00:00Z",
            },
            {
                "name": "azure-landing-zone-tf",
                "full_name": "swthakare0126/azure-landing-zone-tf",
                "html_url": "https://github.com/swthakare0126/azure-landing-zone-tf",
                "description": "Modular CAF Terraform Landing Zone | Hub & Spoke",
                "language": "HCL",
                "fork": False,
                "archived": False,
                "stargazers_count": 7,
                "pushed_at": "2026-11-20T00:00:00Z",
            },
        ]
        out = up.build_repos_section(repos, "swthakare0126/swthakare0126")
        self.assertIn("azure-landing-zone-tf", out)
        self.assertIn(r"Hub & Spoke", out)
        self.assertNotIn("swthakare0126/swthakare0126", out)

    def test_build_activity_section(self) -> None:
        events = [
            {
                "type": "PushEvent",
                "repo": {"name": "swthakare0126/azure-landing-zone-tf"},
                "created_at": "2026-11-24T10:00:00Z",
                "payload": {"ref": "refs/heads/main", "commits": [{}, {}]},
            },
            {
                "type": "CreateEvent",
                "repo": {"name": "swthakare0126/finops-automation"},
                "created_at": "2026-11-23T08:00:00Z",
                "payload": {"ref_type": "repository", "ref": None},
            },
        ]
        out = up.build_activity_section(events)
        self.assertIn("Pushed 2 commits to `main`", out)
        self.assertIn("Created repository", out)

    def test_build_snake_section_toggle(self) -> None:
        disabled = up.build_snake_section("swthakare0126/swthakare0126", False)
        enabled = up.build_snake_section("swthakare0126/swthakare0126", True)
        self.assertIn("<!--", disabled)
        self.assertIn("<picture>", enabled)
        self.assertIn("github-contribution-grid-snake-dark.svg", enabled)

    def test_scan_for_secrets_detects_token_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "leak.txt"
            fake_token = "".join(["g", "h", "p", "_", "A" * 36])
            sample.write_text(f"token = {fake_token}", encoding="utf-8")
            findings = up.scan_for_secrets([sample])
            self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()
