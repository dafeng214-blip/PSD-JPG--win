#!/usr/bin/env python3
"""
PSD 转 JPG - B端专业UI风格
"""

import os
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    print("请先安装 tkinter")
    sys.exit(1)

try:
    from PIL import Image, ImageTk  # 用于生成渐变背景/装饰
except ImportError:
    Image = None
    ImageTk = None

try:
    from converter_core import collect_psd_files, psd_to_jpg
except ImportError:
    print("请先安装依赖: pip install psd-tools pillow")
    sys.exit(1)


try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    HAS_DND = False


class PSDConverterApp:
    def __init__(self, root):
        self.root = root
        # 整体窗口约 70%（相对原 920×640）
        self.ui_w = int(920 * 0.7)
        self.ui_h = int(640 * 0.7)
        # 标题带窗口尺寸：若只有「PSD 转 JPG」无尺寸，说明打开的是旧版 .app，请重新打包或运行 .py
        self.root.title(f"PSD 转 JPG · {self.ui_w}×{self.ui_h}")
        self.root.geometry(f"{self.ui_w}x{self.ui_h}")
        self.root.resizable(False, False)
        
        # 居中
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - self.ui_w) // 2
        y = (self.root.winfo_screenheight() - self.ui_h) // 2
        self.root.geometry(f"{self.ui_w}x{self.ui_h}+{x}+{y}")
        
        # 参考图：轻量级简约（浅色背景 + 白色卡片 + 黑色主按钮）
        self.primary_color = "#111827"  # 主按钮（深黑）
        self.accent_cyan = "#3b82f6"
        self.bg_dark = "#f3f4f6"  # 外层背景
        self.bg_card = "#ffffff"  # 主卡片
        self.bg_input = "#ffffff"  # 拖拽区背景
        self.text_primary = "#111827"
        self.text_secondary = "#6b7280"
        self.border_color = "#e5e7eb"
        self.focus_border = "#3b82f6"
        self.btn_text_on_primary = "#ffffff"
        self.btn_secondary_bg = "#f3f4f6"
        
        self.root.configure(bg=self.bg_dark)
        
        self.selected_path = ""
        self.total_files = 0
        # 多次拖拽/选择累计的目标：PSD 文件 或 含 PSD 的目录
        self.targets = []
        self.quality_var = tk.IntVar(value=100)
        self.recursive_var = tk.BooleanVar(value=False)
        self._drop_hint_override = None
        self._hint_main_id = None
        self._hint_sub_id = None
        
        self.create_widgets()

    def _parse_dnd_paths(self, event_data):
        """
        Parse tkinterdnd2 event.data into a list of filesystem paths.
        On macOS it is commonly a Tcl list-like string: "{/path one} {/path2}".
        """
        try:
            if isinstance(event_data, (list, tuple)):
                raw_paths = [str(x) for x in event_data]
            else:
                raw_paths = self.root.tk.splitlist(event_data)
        except Exception:
            # Fallback: best-effort split.
            raw_paths = str(event_data).split()

        paths = []
        for p in raw_paths:
            p = (p or "").strip()
            if not p:
                continue
            # Sometimes wrapped with braces.
            p = p.strip("{}")
            paths.append(p)
        return paths

    def _to_abs(self, p: str) -> str:
        try:
            return str(Path(p).expanduser().resolve())
        except Exception:
            return str(Path(p).expanduser())

    def _normalize_targets(self, paths):
        valid = []
        for p in paths:
            if not p:
                continue
            pp = Path(p)
            if pp.is_dir() or (pp.is_file() and pp.suffix.lower() == ".psd"):
                valid.append(str(pp))
        return valid

    def _draw_uploader_hint_texts(self, width: int | None = None, height: int | None = None) -> None:
        """在上传 Canvas 上绘制两行提示（不用 Label 叠层，避免 macOS 上点击失效）。"""
        if not hasattr(self, "uploader_canvas"):
            return
        c = self.uploader_canvas
        try:
            w = max(1, width if width is not None else c.winfo_width())
            h = max(1, height if height is not None else c.winfo_height())
        except Exception:
            w, h = 1, 1
        main_txt = self.default_drop_hint if self._drop_hint_override is None else self._drop_hint_override
        sub_txt = "仅支持 PSD 文件格式"
        try:
            if self._hint_main_id is None:
                self._hint_main_id = c.create_text(
                    w / 2,
                    h * 0.56,
                    text=main_txt,
                    font=("Arial", 10, "bold"),
                    fill=self.text_secondary,
                    anchor=tk.CENTER,
                )
            else:
                c.itemconfigure(self._hint_main_id, text=main_txt)
                c.coords(self._hint_main_id, w / 2, h * 0.56)
            if self._hint_sub_id is None:
                self._hint_sub_id = c.create_text(
                    w / 2,
                    h * 0.72,
                    text=sub_txt,
                    font=("Arial", 9),
                    fill=self.text_secondary,
                    anchor=tk.CENTER,
                )
            else:
                c.coords(self._hint_sub_id, w / 2, h * 0.72)
        except Exception:
            pass

    def _render_targets(self) -> None:
        self.selected_path = "|".join(self.targets)
        # 文件列表逐行卡片渲染（替代 Listbox）
        try:
            if hasattr(self, "targets_container"):
                for child in self.targets_container.winfo_children():
                    child.destroy()

                for idx, p in enumerate(self.targets):
                    pp = Path(p)
                    is_dir = pp.is_dir()
                    size_str = ""
                    if not is_dir:
                        try:
                            size_mb = os.path.getsize(pp) / (1024 * 1024)
                            size_str = f"{size_mb:.2f} MB"
                        except Exception:
                            size_str = ""

                    name = pp.name + ("/" if is_dir else "")

                    row_bg = "#f8fafc"
                    row = tk.Frame(
                        self.targets_container,
                        bg=row_bg,
                        highlightthickness=1,
                        highlightbackground=self.border_color,
                    )
                    row.pack(fill=tk.X, padx=8, pady=(6, 4))
                    row.grid_columnconfigure(1, weight=1)

                    left_icon = tk.Frame(row, bg="#f3f4f6", width=36, height=36)
                    left_icon.grid(row=0, column=0, padx=(10, 10), pady=0, sticky="ns")
                    left_icon.grid_propagate(False)
                    tk.Label(left_icon, text="🗂️", bg="#f3f4f6", fg=self.text_secondary, font=("Arial", 12)).pack(fill=tk.BOTH, expand=True)

                    text_wrap = tk.Frame(row, bg=self.bg_card)
                    text_wrap.grid(row=0, column=1, padx=(0, 0), pady=0, sticky="w")
                    tk.Label(text_wrap, text=name, bg=row_bg, fg=self.text_primary, font=("Arial", 11)).pack(anchor="w")
                    tk.Label(text_wrap, text=size_str, bg=row_bg, fg=self.text_secondary, font=("Arial", 9)).pack(anchor="w")

                    # 右侧删除按钮（×）：用 grid 固定列，避免被 pack+expand 挤出可视区
                    rm_btn = tk.Button(
                        row,
                        text="×",
                        command=lambda i=idx: self._delete_target(i),
                        bg=row_bg,
                        fg=self.text_primary,
                        bd=0,
                        relief=tk.FLAT,
                        highlightthickness=0,
                        font=("Arial", 12, "bold"),
                        padx=6,
                        pady=2,
                        cursor="hand2",
                        activebackground=row_bg,
                        activeforeground=self.text_primary,
                    )
                    rm_btn.grid(row=0, column=2, padx=(0, 10), pady=0, sticky="e")
        except Exception:
            pass

        # header text
        if not self.targets:
            self.files_label.config(text="文件列表 (0)")
        elif len(self.targets) == 1:
            self.files_label.config(text=f"文件列表 (1)")
        else:
            self.files_label.config(text=f"文件列表 ({len(self.targets)})")

        enable = tk.NORMAL if self.targets else tk.DISABLED
        if hasattr(self, "convert_btn"):
            convert_fg = self.btn_text_on_primary if enable == tk.NORMAL else "#9ca3af"
            self.convert_btn.config(
                text=f"开始转换 ({len(self.targets)})" if enable == tk.NORMAL else "开始转换",
                bg=self.primary_color,  # 背景始终保持黑色
                fg=convert_fg,
            )
        if hasattr(self, "clear_btn"):
            clear_fg = self.btn_text_on_primary if enable == tk.NORMAL else "#9ca3af"
            self.clear_btn.config(
                bg=self.primary_color,  # 背景始终保持黑色
                fg=clear_fg,
            )
        # 列表交互由每行右侧按钮触发；无需 Listbox 选择逻辑
        if hasattr(self, "drop_frame") and hasattr(self, "selected_panel"):
            # 无文件时上传区吃掉中间余量；有文件时把空间让给列表
            if self.targets:
                self.drop_frame.pack_configure(expand=False, fill=tk.X)
                if not self.selected_panel.winfo_manager():
                    self.selected_panel.pack(fill=tk.X, expand=False, pady=(8, 0))
                else:
                    self.selected_panel.pack_configure(fill=tk.X, expand=False, pady=(8, 0))
            else:
                self.drop_frame.pack_configure(expand=True, fill=tk.BOTH)
                if self.selected_panel.winfo_manager():
                    self.selected_panel.pack_forget()
        self._apply_list_viewport_height()
        self.root.after_idle(self._apply_list_viewport_height)

    def _apply_list_viewport_height(self) -> None:
        """列表 Canvas 视口高度：根据实际内容高度裁剪，避免裁切删除按钮。"""
        if getattr(self, "_list_h_syncing", False):
            return
        if not hasattr(self, "targets_scroll_canvas"):
            return
        c = self.targets_scroll_canvas
        n = len(self.targets)
        self._list_h_syncing = True
        try:
            # 强制刷新一次 bbox（避免滚动区域计算时高度不一致）
            c.update_idletasks()
            bbox = c.bbox("all")
            content_h = (bbox[3] - bbox[1]) if bbox else 0

            if n == 0:
                h = self._list_empty_h
            else:
                # 超出上限走内部滚动；不再使用“估算的行高”来计算，避免部分行被裁切
                h = min(self._list_max_h, max(self._list_empty_h, content_h))

            try:
                cur_h = int(float(c.cget("height")))
            except Exception:
                cur_h = -1
            if cur_h != h:
                c.configure(height=h)
                c.update_idletasks()
        finally:
            self._list_h_syncing = False
        self._update_list_scrollregion()

    def _update_list_scrollregion(self) -> None:
        if not hasattr(self, "targets_scroll_canvas"):
            return
        c = self.targets_scroll_canvas
        n = len(self.targets)
        c.update_idletasks()
        bbox = c.bbox("all")
        if bbox:
            c.configure(scrollregion=bbox)
        else:
            c.configure(scrollregion=(0, 0, 1, 1))
        try:
            H = int(float(c.cget("height")))
        except Exception:
            H = self._list_empty_h
        content_h = (bbox[3] - bbox[1]) if bbox else 0
        if not hasattr(self, "list_scrollbar"):
            return
        if n == 0:
            self.list_scrollbar.pack_forget()
        elif content_h > H + 4:
            self.list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.list_scrollbar.pack_forget()

    def _recompute_total_files(self) -> None:
        if not self.targets:
            self.total_files = 0
            self.progress.config(maximum=1)
            self.progress_label.config(text="")
            return
        psd_files = collect_psd_files([Path(p) for p in self.targets], recursive=False)
        self.total_files = len(psd_files)
        self.progress.config(maximum=self.total_files if self.total_files else 1)

    def _set_targets(self, paths, replace: bool) -> None:
        new_targets = self._normalize_targets(paths)
        if replace:
            self.targets = []

        if not new_targets:
            self.targets = []
            self._render_targets()
            self._recompute_total_files()
            return

        existing_abs = {self._to_abs(x) for x in self.targets}
        for p in new_targets:
            ap = self._to_abs(p)
            if ap in existing_abs:
                continue
            self.targets.append(p)
            existing_abs.add(ap)

        self._render_targets()
        self._recompute_total_files()

    def _delete_target(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.targets):
            return
        self.targets.pop(idx)
        self._render_targets()
        self._recompute_total_files()

    def _delete_selected_target(self) -> None:
        # 兼容旧逻辑：现在是每行右侧按钮删除
        return

    def _on_listbox_select(self) -> None:
        return
    
    def create_widgets(self):
        # ===== 全局样式/背景 =====
        try:
            style = ttk.Style()
            # 尽量使用可控的深色样式
            if "clam" in style.theme_names():
                style.theme_use("clam")
            # 进度条/滑条：尽量做成浅色底+黑色填充
            style.configure(
                "Custom.Horizontal.TProgressbar",
                troughcolor=self.btn_secondary_bg,
                background=self.primary_color,
                thickness=8,
            )
        except Exception:
            pass

        # 轻量级简约：背景改为纯色（避免过多装饰影响按钮可见性）
        if Image is not None and ImageTk is not None:
            try:
                bg_label = tk.Label(self.root, bg=self.bg_dark, bd=0)
                bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            except Exception:
                pass

        # ===== 主卡片容器 =====
        main_card = tk.Frame(
            self.root,
            bg=self.bg_card,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.border_color,
        )
        main_card.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        # 中间区域与底栏分离：底栏先贴主窗口底部，避免文件多时把按钮挤出可视区
        body = tk.Frame(main_card, bg=self.bg_card)
        self.body_frame = body
        
        # ===== 标题 =====
        header = tk.Frame(body, bg=self.bg_card)
        header.pack(fill=tk.X, pady=(0, 10))
        
        # 顶部 Wolf 图标（用文本占位，保持轻量）
        icon_wrap = tk.Frame(header, bg="#111827", width=28, height=28)
        icon_wrap.pack(side=tk.LEFT, padx=(0, 10))
        icon_wrap.pack_propagate(False)
        tk.Label(icon_wrap, text="🐺", bg="#111827", fg=self.btn_text_on_primary, font=("Arial", 14)).pack(
            fill=tk.BOTH, expand=True
        )

        tk.Label(
            header,
            text="PSD 转 JPG",
            font=("Arial", 13, "bold"),
            bg=self.bg_card,
            fg=self.text_primary,
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="快速转换您的PSD文件",
            font=("Arial", 9),
            bg=self.bg_card,
            fg=self.text_secondary,
        ).pack(side=tk.LEFT, padx=(8, 0))
        tk.Frame(header, bg=self.border_color, height=1).pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        # ===== 拖拽区域 =====
        drop_frame = tk.Frame(
            body,
            bg=self.bg_input,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.border_color,
        )
        # 无文件时让上传区吃掉中间余量；有文件时改为不扩展，把空间留给列表（在 _render_targets 里切换）
        drop_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        
        # 上传区域：Canvas 虚线框 + 中间上传图标 + 两行说明（更接近你给的截图）
        drop_frame.pack_propagate(False)
        drop_frame.configure(height=int(170 * 0.7))

        self.uploader_canvas = tk.Canvas(
            drop_frame,
            bg=self.bg_input,
            highlightthickness=0,
        )
        self.uploader_canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self.uploader_canvas.update_idletasks()
        c_w = max(1, self.uploader_canvas.winfo_width())
        c_h = max(1, self.uploader_canvas.winfo_height())
        # 内层虚线框（更贴近截图：带更大的内边距）
        inset_x = int(44 * 0.7)
        inset_y = int(34 * 0.7)
        self.uploader_canvas.create_rectangle(
            inset_x,
            inset_y,
            c_w - inset_x,
            c_h - inset_y,
            outline="#cbd5e1",
            width=2,
            dash=(4, 4),
        )

        # 灰色“上传”图标框：随 Canvas 尺寸变化重绘，保证居中且不跑偏
        self._uploader_icon_tag = "uploader_icon"

        def _draw_uploader_icon(icon_w: int, icon_h: int) -> None:
            c = self.uploader_canvas
            c.delete(self._uploader_icon_tag)
            cx = icon_w * 0.5
            # 让图标位于“点击上传”文字上方（而不是过高）
            cy = icon_h * 0.40
            box_w = int(62 * 0.7)
            box_h = int(48 * 0.7)
            x1 = cx - box_w / 2
            y1 = cy - box_h / 2
            x2 = cx + box_w / 2
            y2 = cy + box_h / 2
            r = max(6, int(12 * 0.7))

            # 背景圆角矩形（近似）
            c.create_rectangle(x1 + r, y1, x2 - r, y2, fill="#e5e7eb", outline="", tags=(self._uploader_icon_tag,))
            c.create_rectangle(x1, y1 + r, x2, y2 - r, fill="#e5e7eb", outline="", tags=(self._uploader_icon_tag,))
            c.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill="#e5e7eb", outline="", tags=(self._uploader_icon_tag,))
            c.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill="#e5e7eb", outline="", tags=(self._uploader_icon_tag,))
            c.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill="#e5e7eb", outline="", tags=(self._uploader_icon_tag,))
            c.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill="#e5e7eb", outline="", tags=(self._uploader_icon_tag,))

            # 箭头（上箭头）
            arrow_color = "#111827"
            c.create_line(cx, y1 + 18, cx, y1 + 12, width=3, fill=arrow_color, tags=(self._uploader_icon_tag,))
            c.create_line(cx, y1 + 12, cx - 8, y1 + 20, width=3, fill=arrow_color, tags=(self._uploader_icon_tag,))
            c.create_line(cx, y1 + 12, cx + 8, y1 + 20, width=3, fill=arrow_color, tags=(self._uploader_icon_tag,))

        _draw_uploader_icon(c_w, c_h)

        self.default_drop_hint = (
            "点击 上传 或拖拽文件/文件夹"
            if HAS_DND
            else "点击 上传 或选择文件/文件夹（拖拽需 tkinterdnd2）"
        )
        # 用 Canvas 文字代替叠在 Canvas 上的 Label（macOS 上子控件常导致点击/拖拽异常）
        self._draw_uploader_hint_texts()

        def _on_uploader_canvas_configure(event):
            if event.widget is not self.uploader_canvas:
                return
            if event.width < 4 or event.height < 4:
                return
            _draw_uploader_icon(event.width, event.height)
            self._draw_uploader_hint_texts(width=event.width, height=event.height)

        self.uploader_canvas.bind("<Configure>", _on_uploader_canvas_configure)

        # 绑定点击：整块上传区点击打开文件选择
        self.drop_frame = drop_frame

        def _on_upload_area_click(_event=None):
            self.select_files()

        for _w in (drop_frame, self.uploader_canvas):
            _w.bind("<Button-1>", _on_upload_area_click)
        self.uploader_canvas.config(cursor="hand2")

        if HAS_DND:
            # Only register the key widgets to reduce platform-specific event loss.
            for w in (self.root, self.drop_frame):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.handle_drop)
                    w.dnd_bind("<<DragEnter>>", self.handle_drag_enter)
                    w.dnd_bind("<<DragLeave>>", self.handle_drag_leave)
                except Exception:
                    pass
        
        # ===== 已选择内容显示 =====
        selected_panel = tk.Frame(
            body,
            bg=self.bg_card,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.border_color,
        )
        self.selected_panel = selected_panel
        # 初始不展示文件列表：首次上传后在 _render_targets 中再 pack
        if self.targets:
            selected_panel.pack(fill=tk.X, expand=False, pady=(8, 0))

        self.files_label = tk.Label(
            selected_panel,
            text="文件列表 (0)",
            font=("Arial", 10),
            bg=self.bg_card,
            fg=self.text_primary,
            justify=tk.LEFT,
            anchor=tk.W,
            padx=12,
            pady=8,
        )
        self.files_label.pack(fill=tk.X)

        list_frame = tk.Frame(selected_panel, bg=self.bg_card)
        self.list_frame = list_frame
        list_frame.pack(fill=tk.X, expand=False, padx=8, pady=(0, 8))

        # 可滚动逐行卡片列表（固定可视高度，内容超出后滚动）
        list_canvas = tk.Canvas(list_frame, bg=self.bg_card, highlightthickness=0, height=1)
        list_canvas.pack(side=tk.LEFT, fill=tk.X, expand=False)

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=list_canvas.yview)
        self.list_scrollbar = scrollbar
        list_canvas.configure(yscrollcommand=scrollbar.set)

        self.targets_scroll_canvas = list_canvas
        self.targets_container = tk.Frame(list_canvas, bg=self.bg_card)
        self.targets_container_window = list_canvas.create_window((0, 0), window=self.targets_container, anchor="nw")
        self._list_empty_h = int(56 * 0.7)
        self._list_row_h = int(52 * 0.7)
        self._list_max_h = int(200 * 0.7)

        def _on_frame_configure(_event):
            self._update_list_scrollregion()

        self.targets_container.bind("<Configure>", _on_frame_configure)

        def _on_list_frame_configure(event):
            if event.widget is not self.list_frame:
                return
            if getattr(self, "_last_list_frame_h", -1) == event.height:
                return
            self._last_list_frame_h = event.height
            self._apply_list_viewport_height()

        list_frame.bind("<Configure>", _on_list_frame_configure)
        # 允许画布宽度跟随容器
        def _on_canvas_resize(_event):
            try:
                list_canvas.itemconfigure(self.targets_container_window, width=list_canvas.winfo_width())
            except Exception:
                pass

        list_canvas.bind("<Configure>", _on_canvas_resize)

        # 支持鼠标/触控板上下滚动（macOS/Windows）
        def _on_list_mousewheel(event):
            try:
                if getattr(event, "num", None) == 4:
                    list_canvas.yview_scroll(-1, "units")
                elif getattr(event, "num", None) == 5:
                    list_canvas.yview_scroll(1, "units")
                else:
                    delta = getattr(event, "delta", 0)
                    if delta == 0:
                        return
                    # Tk: delta 通常是 120 的倍数；delta>0 往上滚
                    units = int(-1 * (delta / 120))
                    if units != 0:
                        list_canvas.yview_scroll(units, "units")
                return "break"
            except Exception:
                return "break"

        list_canvas.bind("<MouseWheel>", _on_list_mousewheel)
        list_canvas.bind("<Button-4>", _on_list_mousewheel)
        list_canvas.bind("<Button-5>", _on_list_mousewheel)

        # ===== 下方固定控制区（质量 + 进度 + 按钮）=====
        bottom_controls = tk.Frame(main_card, bg=self.bg_card)
        self.bottom_controls = bottom_controls
        bottom_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        # ===== 转换选项 =====
        options_frame = tk.Frame(bottom_controls, bg=self.bg_card)
        options_frame.pack(fill=tk.X, pady=(0, 8))

        quality_row = tk.Frame(options_frame, bg=self.bg_card)
        quality_row.pack(fill=tk.X, pady=(6, 0))

        self.quality_label = tk.Label(
            quality_row,
            text="图片质量",
            font=("Arial", 10),
            bg=self.bg_card,
            fg=self.text_secondary,
        )
        self.quality_label.pack(side=tk.LEFT, padx=12)

        self.quality_scale = ttk.Scale(
            quality_row,
            from_=50,
            to=100,
            orient="horizontal",
            length=int(260 * 0.7),
            value=self.quality_var.get(),
            command=self._on_quality_change,
        )
        self.quality_scale.pack(side=tk.RIGHT, padx=12, fill=tk.X, expand=True)

        self.quality_value_label = tk.Label(
            quality_row,
            text=str(self.quality_var.get()),
            font=("Arial", 10, "bold"),
            bg=self.bg_card,
            fg=self.text_primary,
        )
        self.quality_value_label.pack(side=tk.RIGHT, padx=(0, 16))

        # 递归处理子文件夹：当前需求默认不递归，因此不在界面展示该选项
        
        # ===== 进度条 =====
        progress_frame = tk.Frame(bottom_controls, bg=self.bg_card)
        progress_frame.pack(fill=tk.X, pady=(4, 0))
        
        self.progress = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            length=int(520 * 0.7),
            style="Custom.Horizontal.TProgressbar",
        )
        self.progress.pack(fill=tk.X)
        
        self.progress_label = tk.Label(progress_frame, text="",
                                    font=("Arial", 9),
                                    bg=self.bg_card, fg=self.text_secondary)
        self.progress_label.pack(pady=(4, 0))
        
        # ===== 底部按钮栏（固定在下方）=====
        footer = tk.Frame(bottom_controls, bg=self.bg_card)
        
        # 左侧：清空按钮（用 Label 实现，避免 macOS Tk/Button 的禁用态颜色覆盖）
        self.clear_btn = tk.Label(
            footer,
            text="清空列表",
            font=("Arial", 13),
            bg=self.primary_color,
            fg=self.btn_text_on_primary,
            bd=0,
            padx=28,
            pady=12,
            cursor="hand2",
        )
        self.clear_btn.pack(side=tk.LEFT)
        self.clear_btn.bind("<Button-1>", lambda _e: self.clear_selection())

        # 删除单个目标（仅移除列表中的当前项）
        self.delete_one_btn = tk.Button(
            footer,
            text="删除选中",
            command=self._delete_selected_target,
            font=("Arial", 11),
            bg=self.bg_card,
            fg=self.text_secondary,
            bd=1,
            relief=tk.SOLID,
            highlightbackground=self.border_color,
            padx=16,
            pady=6,
            cursor="hand2",
            state=tk.DISABLED,
        )
        # UI风格参考图：不显示“删除选中”按钮，改为双击列表项删除
        # 仍保留按钮以不改变功能入口。
        self.delete_one_btn.pack_forget()
        
        # 右侧：开始转换按钮（用 Label 实现，确保背景始终为黑色）
        self.convert_btn = tk.Label(
            footer,
            text="开始转换",
            font=("Arial", 13, "bold"),
            bg=self.primary_color,
            fg=self.btn_text_on_primary,
            bd=0,
            padx=36,
            pady=12,
            cursor="hand2",
        )
        self.convert_btn.pack(side=tk.RIGHT)
        self.convert_btn.bind("<Button-1>", lambda _e: self.start_convert())

        footer.pack(fill=tk.X, pady=(10, 0))
        body.pack(fill=tk.BOTH, expand=True)

        # 初始空列表：压扁列表区域高度
        self._apply_list_viewport_height()
        self.root.after_idle(self._apply_list_viewport_height)

    def _on_quality_change(self, _value):
        # ttk.Scale 回调传入字符串/浮点值，这里把它格式化成整数质量。
        try:
            q = int(float(_value))
        except Exception:
            q = self.quality_var.get()
        self.quality_var.set(q)
        self.quality_value_label.config(text=str(q))
    
    def select_files(self):
        paths = filedialog.askopenfilenames(title="选择 PSD 文件（可多选）",
                                        filetypes=[("PSD 文件", "*.psd"), ("所有文件", "*.*")])
        
        if paths:
            self.handle_selected_paths(paths)
            return
        # 如果用户取消了文件选择，就不再自动弹出“选择文件夹”。
        # 需要转换文件夹时，请使用拖拽文件夹，或后续我们再加“单独选择文件夹”按钮。
        return
    
    def handle_selected_paths(self, paths):
        if not paths:
            return

        if isinstance(paths, str):
            paths = [paths]

        paths = [p for p in paths if p and str(p).strip()]
        self._set_targets(paths, replace=True)
    
    def handle_selected_path(self, path):
        if not path:
            return
        if not (os.path.isdir(path) or (os.path.isfile(path) and str(path).lower().endswith(".psd"))):
            messagebox.showwarning("提示", "请选择 PSD 文件或文件夹")
            return

        self._set_targets([path], replace=True)
        if os.path.isdir(path) and self.total_files == 0:
            messagebox.showwarning("提示", "文件夹中没有 PSD 文件")
            self._set_targets([], replace=True)

    def handle_drop(self, event):
        # 在界面上显示接收信息，便于确认拖拽事件是否触发。
        try:
            self._drop_hint_override = "已接收拖拽，解析中..."
            self._draw_uploader_hint_texts()
        except Exception:
            pass
        paths = self._parse_dnd_paths(getattr(event, "data", ""))

        def _reset_drop_hint():
            try:
                self._drop_hint_override = None
                self._draw_uploader_hint_texts()
            except Exception:
                pass

        if not paths:
            _reset_drop_hint()
            return

        valid_items = self._normalize_targets(paths)
        if not valid_items:
            messagebox.showwarning("提示", "仅支持拖入 PSD 文件或文件夹")
            _reset_drop_hint()
            return

        # 多次拖拽：追加目标
        self._set_targets(valid_items, replace=False)
        _reset_drop_hint()

    def handle_drag_enter(self, event):
        try:
            self._drop_hint_override = "松手以导入（PSD文件/文件夹）"
            self._draw_uploader_hint_texts()
        except Exception:
            pass
        try:
            self.drop_frame.config(bg=self.bg_card)
        except Exception:
            pass
    
    def handle_drag_leave(self, event):
        try:
            self._drop_hint_override = None
            self._draw_uploader_hint_texts()
        except Exception:
            pass
        try:
            self.drop_frame.config(bg=self.bg_input)
        except Exception:
            pass
    
    def clear_selection(self):
        self.targets = []
        self._render_targets()
        self._recompute_total_files()
    
    def start_convert(self):
        if not self.targets:
            return
        if not all(os.path.exists(p.strip()) for p in self.targets):
            messagebox.showerror("错误", "路径不存在")
            return
        
        self.convert_btn.config(
            text="转换中...",
            bg=self.primary_color,
            fg=self.btn_text_on_primary,
        )
        self.clear_btn.config(
            bg=self.primary_color,
            fg="#9ca3af",
        )
        try:
            self.delete_one_btn.config(state=tk.DISABLED)
        except Exception:
            pass
        self.progress['value'] = 0
        
        thread = threading.Thread(target=self.convert)
        thread.daemon = True
        thread.start()
    
    def convert(self):
        success = 0
        failed = 0
        psd_files = collect_psd_files([Path(p) for p in self.targets], recursive=False)
        first = Path(self.targets[0])
        output_dir = (first.parent / 'output') if first.is_file() else (first / 'output')
        
        self.total_files = len(psd_files)
        
        if not psd_files:
            self.root.after(0, self.show_result, 0, 0, "没有找到 PSD 文件")
            return
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.root.after(0, lambda: self.progress.config(maximum=self.total_files))
        
        for i, psd_file in enumerate(psd_files):
            output_file = output_dir / f"{psd_file.stem}.jpg"
            
            self.root.after(0, lambda n=i, f=psd_file.name: self.update_progress(n, f))
            
            ok, error = psd_to_jpg(psd_file, output_file, quality=self.quality_var.get())
            if ok:
                success += 1
            else:
                failed += 1
            
            self.root.after(0, lambda v=i+1: self.progress.config(value=v))
        
        self.root.after(0, lambda: self.show_result(success, failed, str(output_dir)))
    
    def update_progress(self, index, filename):
        self.progress_label.config(text=f"正在转换: {filename} ({index+1}/{self.total_files})")
    
    def show_result(self, success, failed, output_dir):
        self.convert_btn.config(text="开始转换", bg=self.primary_color, fg=self.btn_text_on_primary)
        
        if success > 0:
            messagebox.showinfo("完成 ✅", f"转换成功！\n\n✅ 成功: {success} 个\n❌ 失败: {failed} 个\n\n📁 {output_dir}")
        else:
            messagebox.showwarning("完成", f"没有成功转换的文件")
        
        self.clear_selection()
        self.progress['value'] = 0
        self.progress_label.config(text="")


def main():
    root = None
    if HAS_DND:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = tk.Tk()
            try:
                messagebox.showwarning(
                    "提示",
                    "拖拽功能初始化失败，已退回普通窗口。\n仍可使用点击上传选择文件。",
                )
            except Exception:
                pass
    else:
        root = tk.Tk()
    PSDConverterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
