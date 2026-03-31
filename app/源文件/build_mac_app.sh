#!/bin/bash
# 重新打包 macOS 应用。修改 batch_psd_to_jpg_gui.py 后必须执行本脚本，
# 否则双击 PSD转JPG.app 仍是旧界面（.app 内嵌的是打包时的代码，不会自动更新）。
set -euo pipefail
cd "$(dirname "$0")"

if ! python3 -c "import PyInstaller" 2>/dev/null; then
  echo "请先安装: python3 -m pip install --user pyinstaller"
  exit 1
fi

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name "PSD转JPG" \
  --collect-all tkinterdnd2 \
  batch_psd_to_jpg_gui.py

if [[ -d "PSD转JPG.app" ]]; then
  rm -rf "PSD转JPG.app.bak"
  mv "PSD转JPG.app" "PSD转JPG.app.bak"
  echo "已备份旧版为 PSD转JPG.app.bak"
fi
mv "dist/PSD转JPG.app" .
rm -rf build dist
echo "完成。请双击本目录下的 PSD转JPG.app（标题应含 644×448）。"
