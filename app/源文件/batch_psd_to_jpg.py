#!/usr/bin/env python3
"""
批量将 PSD 转换为 JPG
支持单个文件或文件夹，会自动在源文件所在目录创建 output 文件夹
使用方法: 
    python3 batch_psd_to_jpg.py 文件.psd
    python3 batch_psd_to_jpg.py /path/to/folder
"""

import os
import sys
from pathlib import Path

try:
    from converter_core import collect_psd_files, psd_to_jpg
except ImportError:
    print("请先安装依赖: pip install psd-tools pillow")
    sys.exit(1)


def process_path(input_path):
    """处理单个文件或文件夹"""
    input_path = Path(input_path)
    
    # 转换成功统计
    success = 0
    failed = 0
    
    if input_path.is_file() and input_path.suffix.lower() == '.psd':
        # 单个文件
        output_dir = input_path.parent / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{input_path.stem}.jpg"
        
        print(f"处理: {input_path.name}")
        ok, error = psd_to_jpg(input_path, output_file)
        if ok:
            print(f"  → {output_file}")
            success += 1
        else:
            print(f"  ✗ {error}")
            failed += 1
    
    elif input_path.is_dir():
        # 文件夹
        output_dir = input_path / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找所有 PSD 文件（排除 ._ 开头的 macOS 临时文件）
        psd_files = collect_psd_files([input_path])
        
        if not psd_files:
            print(f"在 {input_path} 中没有找到 PSD 文件")
            return 0, 0
        
        print(f"找到 {len(psd_files)} 个 PSD 文件")
        print(f"输出目录: {output_dir}\n")
        
        for psd_file in psd_files:
            output_file = output_dir / f"{psd_file.stem}.jpg"
            print(f"处理: {psd_file.name} ...", end=' ')
            
            ok, error = psd_to_jpg(psd_file, output_file)
            
            if ok:
                print("✓")
                success += 1
            else:
                print(f"✗ ({error})")
                failed += 1
    
    else:
        print(f"无效的路径: {input_path}")
        return 0, 0
    
    return success, failed


def main():
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
    else:
        input_path = os.getcwd()
    
    print(f"输入路径: {input_path}\n")
    
    success, failed = process_path(input_path)
    
    print(f"\n完成! 成功: {success}, 失败: {failed}")
    if success > 0:
        print(f"JPG 保存在源文件所在目录的 output 文件夹中")


if __name__ == '__main__':
    main()
