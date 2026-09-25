from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from xsd_model_builder import paths
from xsd_model_builder.cli import main


SIMPLE_SCHEMA = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="documento" type="xs:string"/>
</xs:schema>"""


class OutputPathTests(unittest.TestCase):
    def test_source_default_is_project_root_output_folder(self) -> None:
        project_dir = Path(__file__).resolve().parents[1]
        self.assertEqual(project_dir / "Modelos XML Gerados", paths.default_output_directory())

    def test_executable_in_dist_uses_parent_project_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "dist" / "XsdXmlBuilder.exe"
            with patch.object(paths.sys, "frozen", True, create=True):
                with patch.object(paths.sys, "platform", "win32"):
                    with patch.object(paths.sys, "executable", str(executable)):
                        self.assertEqual(
                            Path(directory) / "Modelos XML Gerados",
                            paths.default_output_directory(),
                        )

    def test_macos_app_uses_documents_outside_app_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            executable = Path(directory) / "XsdXmlBuilder.app" / "Contents" / "MacOS" / "XsdXmlBuilder"
            with patch.object(paths.sys, "frozen", True, create=True):
                with patch.object(paths.sys, "platform", "darwin"):
                    with patch.object(paths.sys, "executable", str(executable)):
                        with patch.object(paths.Path, "home", return_value=home):
                            self.assertEqual(
                                home / "Documents" / "Modelos XML Gerados",
                                paths.default_output_directory(),
                            )

    def test_linux_executable_uses_documents_outside_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            executable = Path(directory) / "bin" / "XsdXmlBuilder"
            with patch.object(paths.sys, "frozen", True, create=True):
                with patch.object(paths.sys, "platform", "linux"):
                    with patch.object(paths.sys, "executable", str(executable)):
                        with patch.object(paths.Path, "home", return_value=home):
                            self.assertEqual(
                                home / "Documents" / "Modelos XML Gerados",
                                paths.default_output_directory(),
                            )

    def test_manually_chosen_folder_is_preserved_when_root_changes(self) -> None:
        chosen = Path("outros-modelos") / "arquivo.xml"
        self.assertEqual(
            chosen.parent / "NFe-modelo-completo.xml",
            paths.suggested_output_path("NFe", str(chosen)),
        )

    def test_cli_without_output_writes_to_default_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "documento.xsd"
            output = Path(directory) / "Modelos XML Gerados" / "documento-modelo-completo.xml"
            schema.write_text(SIMPLE_SCHEMA, encoding="utf-8")
            with patch("xsd_model_builder.cli.suggested_output_path", return_value=output):
                with redirect_stdout(io.StringIO()):
                    exit_code = main(["--schema", str(schema)])
            self.assertEqual(0, exit_code)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
