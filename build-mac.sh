#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'Este script precisa ser executado no macOS.\n' >&2
    exit 1
fi

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

python_bin="${PYTHON_BIN:-python3}"
venv_dir="$project_dir/.build-venv-macos"
"$python_bin" -m venv "$venv_dir"
venv_python="$venv_dir/bin/python"

"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -e '.[build]'
"$venv_python" -c 'import tkinter; import lxml.etree'

"$venv_python" -m PyInstaller \
    --noconfirm \
    --clean \
    --onedir \
    --windowed \
    --name "XSD XML Builder - By Jonatas Oliveira" \
    --paths "$project_dir/src" \
    --collect-all lxml \
    --workpath "$project_dir/build/macos" \
    --specpath "$project_dir/build/macos-spec" \
    --distpath "$project_dir/dist" \
    "$project_dir/src/xsd_model_builder/gui_entry.py"

app_path="$project_dir/dist/XSD XML Builder - By Jonatas Oliveira.app"
if [[ ! -d "$app_path" ]]; then
    printf 'O aplicativo não foi encontrado em: %s\n' "$app_path" >&2
    exit 1
fi
printf 'Aplicativo criado em: %s\n' "$app_path"
