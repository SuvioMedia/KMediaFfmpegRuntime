# SPDX-License-Identifier: LGPL-2.1-or-later

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "fetch_sources", ROOT / "scripts/fetch_sources.py"
)
FETCH = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(FETCH)


class FetchSourcesTest(unittest.TestCase):
    def test_fetches_closed_hash_verified_inventory_and_ffmpeg_evidence(self):
        expected_hashes = {
            FETCH.build.load_json(ROOT / f"compliance/components/{component}.json")[
                "sourceArchive"
            ]: FETCH.build.load_json(
                ROOT / f"compliance/components/{component}.json"
            )["sourceSha256"]
            for component in FETCH.build.COMPONENTS
        }

        def download(_url: str, destination: Path) -> None:
            destination.write_bytes(b"input")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sources"
            with (
                mock.patch.object(FETCH.build, "download", side_effect=download) as invoke,
                mock.patch.object(
                    FETCH.build,
                    "sha256",
                    side_effect=lambda path: expected_hashes[path.name],
                ),
            ):
                FETCH.fetch_sources(output)

            self.assertEqual(len(FETCH.build.COMPONENTS) + 2, invoke.call_count)
            self.assertEqual(
                set(expected_hashes) | {"ffmpeg-9.0.1.tar.xz.asc", "ffmpeg-devel.asc"},
                {path.name for path in output.iterdir()},
            )

    def test_rejects_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "already exists"):
                FETCH.fetch_sources(Path(directory))


if __name__ == "__main__":
    unittest.main()
