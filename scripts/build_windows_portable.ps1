# Build a portable Windows folder with PyInstaller (CI artifact)
$ErrorActionPreference = "Stop"
python -m pip install -U pip wheel
pip install -e ".[installer]"
pyinstaller --noconfirm --onefile --name bunker `
  --collect-all=keyring `
  --collect-all=tzdata `
  --collect-submodules bunker `
  scripts/pyinstaller_entry.py
New-Item -ItemType Directory -Force -Path dist/portable | Out-Null
Copy-Item dist/bunker.exe dist/portable/
Copy-Item -Recurse config dist/portable/config
Write-Host "Portable build at dist/portable"