#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    printf 'Este script precisa ser executado no Linux.\n' >&2
    exit 1
fi

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

python_bin="${PYTHON_BIN:-python3}"
venv_dir="$project_dir/.build-venv-linux"
"$python_bin" -m venv "$venv_dir"
venv_python="$venv_dir/bin/python"

"$venv_python" -c 'import tkinter'
"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -e '.[build]'
"$venv_python" -c 'import lxml.etree'

"$venv_python" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name XsdXmlBuilder \
    --paths "$project_dir/src" \
    --collect-all lxml \
    --workpath "$project_dir/build/linux" \
    --specpath "$project_dir/build/linux-spec" \
    --distpath "$project_dir/dist" \
    "$project_dir/src/xsd_model_builder/gui_entry.py"

executable="$project_dir/dist/XsdXmlBuilder"
if [[ ! -x "$executable" ]]; then
    printf 'O executável não foi encontrado em: %s\n' "$executable" >&2
    exit 1
fi

archive="$project_dir/dist/XsdXmlBuilder-linux-$(uname -m).tar.gz"
tar -C "$project_dir/dist" -czf "$archive" XsdXmlBuilder
printf 'Executável criado em: %s\nPacote criado em: %s\n' "$executable" "$archive"
