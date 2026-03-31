# PSD转JPG工具

## 文件说明

| 文件/文件夹 | 用途 |
|-----------|------|
| `app/` | macOS 版 PSD转JPG（完整源码） |
| `build-windows.yml` | GitHub Actions 构建脚本（推送到 GitHub 后自动生成 Windows exe） |
| `PSD转JPG_Windows.spec` | PyInstaller Windows 打包配置 |
| `batch_psd_to_jpg_gui.py` | Windows 构建用主程序 |
| `converter_core.py` | 转换核心逻辑 |
| `batch_psd_to_jpg.py` | 批量处理入口 |

## 如何构建 Windows exe

**把整个文件夹上传到 GitHub 推送 main 分支，GitHub Actions 会自动构建并发布 exe 下载地址。**

## 依赖

- Python 3.11
- psd-tools
- Pillow
- pyinstaller
