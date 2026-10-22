$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name DeviceViewer --manifest app.manifest --collect-all hid --collect-all pystray --copy-metadata hidapi --copy-metadata pystray --copy-metadata pillow --copy-metadata six main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item -LiteralPath README.md -Destination dist\DeviceViewer\README.md
Copy-Item -LiteralPath LICENSE,THIRD_PARTY_NOTICES.md -Destination dist\DeviceViewer
