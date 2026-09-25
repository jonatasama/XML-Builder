from __future__ import annotations

import sys
from pathlib import Path


OUTPUT_FOLDER_NAME = "Modelos XML Gerados"


def project_root() -> Path:
    """Localiza a raiz do projeto no código-fonte e no executável empacotado."""
    if getattr(sys, "frozen", False):
        executable_directory = Path(sys.executable).resolve().parent
        if executable_directory.name.casefold() == "dist":
            return executable_directory.parent
        return executable_directory
    return Path(__file__).resolve().parents[2]


def default_output_directory() -> Path:
    if getattr(sys, "frozen", False) and sys.platform in {"darwin", "linux"}:
        return Path.home() / "Documents" / OUTPUT_FOLDER_NAME
    return project_root() / OUTPUT_FOLDER_NAME


def suggested_output_path(root_name: str, current: str = "") -> Path:
    folder = Path(current).parent if current.strip() else default_output_directory()
    return folder / f"{root_name}-modelo-completo.xml"
