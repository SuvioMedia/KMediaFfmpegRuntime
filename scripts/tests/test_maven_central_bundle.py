# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "build_maven_central_bundle.py"
SPEC = importlib.util.spec_from_file_location("central", MODULE_PATH)
central = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(central)


class MavenCentralBundleTest(unittest.TestCase):
    def create_staging(self, root: Path, version: str) -> None:
        for artifact, extension in central.ARTIFACTS.items():
            directory = root / central.GROUP / artifact / version
            directory.mkdir(parents=True)
            prefix = f"{artifact}-{version}"
            for name in (
                f"{prefix}.{extension}", f"{prefix}.pom", f"{prefix}-sources.jar",
                f"{prefix}-javadoc.jar", f"{prefix}-corresponding-source.tar.gz",
            ):
                (directory / name).write_bytes(b"test")

    def test_closed_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            version = "0.1.0-rc.1"
            self.create_staging(root, version)
            self.assertEqual(20, len(central.base_files(root, version)))

    def test_normalize_removes_only_gradle_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            version = "0.1.0-rc.1"
            self.create_staging(root, version)
            for artifact, extension in central.ARTIFACTS.items():
                directory = root / central.GROUP / artifact / version
                prefix = f"{artifact}-{version}"
                module = directory / f"{prefix}.module"
                module.write_bytes(b"generated")
                metadata = directory.parent / "maven-metadata.xml"
                metadata.write_bytes(b"generated")
                for path in (*central.required_files(root, version), module, metadata):
                    if path.is_relative_to(directory.parent):
                        for suffix in central.GENERATED_CHECKSUM_SUFFIXES:
                            path.with_name(path.name + suffix).write_bytes(b"generated")
            central.normalize(type("Arguments", (), {"staging": root, "version": version})())
            self.assertEqual(20, len(central.base_files(root, version)))
            actual = {path for path in (root / central.GROUP).rglob("*") if path.is_file()}
            self.assertEqual(set(central.required_files(root, version)), actual)


if __name__ == "__main__":
    unittest.main()
