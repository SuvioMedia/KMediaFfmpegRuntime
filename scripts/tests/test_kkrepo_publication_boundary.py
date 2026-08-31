# SPDX-License-Identifier: LGPL-2.1-or-later

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
PUBLISHER = (ROOT / ".github/scripts/publish_staged_maven.sh").read_text(
    encoding="utf-8"
)


class KkRepoPublicationBoundaryTest(unittest.TestCase):
    def test_publisher_job_is_manual_repository_exact_and_least_privilege(self) -> None:
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("pull_request:", WORKFLOW)
        self.assertNotIn("\n  push:", WORKFLOW)
        self.assertNotIn("\n  schedule:", WORKFLOW)
        self.assertIn("permissions: {}", WORKFLOW)
        self.assertIn("runs-on: suvio-runtime-publisher-amd64", WORKFLOW)
        self.assertIn("github.repository == 'SuvioMedia/KMediaFfmpegRuntime'", WORKFLOW)
        self.assertIn("github.actor == 'Shusek'", WORKFLOW)
        self.assertIn("retention-days: 1", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)

    def test_github_release_is_final_and_owns_the_only_write_permission(self) -> None:
        self.assertEqual(WORKFLOW.count("contents: write"), 1)
        self.assertIn("needs: [readiness, publish-kkrepo]", WORKFLOW)
        self.assertIn(
            "Create immutable GitHub Release after public Maven publication",
            WORKFLOW,
        )
        self.assertLess(
            WORKFLOW.index("publish-kkrepo:"),
            WORKFLOW.index("github-release:"),
        )

    def test_runtime_identity_can_reach_only_public_maven_releases(self) -> None:
        self.assertIn('hosted_repository="suvio-public-releases"', PUBLISHER)
        self.assertIn('group_repository="suvio-maven-public"', PUBLISHER)
        self.assertIn(
            'internal_origin="https://kkrepo-internal.kkrepo.svc.cluster.local"',
            PUBLISHER,
        )
        for forbidden in (
            "suvio-private",
            "snapshot",
            "--request DELETE",
            "docker",
            "internal/security",
            "repo.suviomedia.cc/repository/suvio-public-releases",
        ):
            self.assertNotIn(forbidden, PUBLISHER)

    def test_publisher_is_fail_closed_and_publishes_poms_last(self) -> None:
        for control in (
            "set -euo pipefail",
            "set +x",
            "sha256sum --check --strict --quiet SHA256SUMS",
            "Refusing to replace an existing public runtime path with different bytes.",
            "No automatic PUT retry was attempted.",
            'done <"${upload_payloads}"',
            'done <"${upload_poms}"',
            "repository metadata was intentionally not replaced",
        ):
            self.assertIn(control, PUBLISHER)
        self.assertLess(
            PUBLISHER.index('done <"${upload_payloads}"'),
            PUBLISHER.index('done <"${upload_poms}"'),
        )


if __name__ == "__main__":
    unittest.main()
