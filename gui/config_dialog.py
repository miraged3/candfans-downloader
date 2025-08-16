import copy
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


class ConfigDialog(tk.Toplevel):
    """编辑 config.yaml 的弹窗"""

    def __init__(self, parent, cfg_obj: dict, on_save):
        super().__init__(parent)
        self.title("编辑配置")
        self.transient(parent)
        self.grab_set()  # 模态
        self.resizable(True, True)
        self.on_save = on_save

        # 拷贝一份，避免直接改全局
        self._cfg = copy.deepcopy(cfg_obj or {})

        # ---- 基础字段 ----
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=12, pady=12)

        def add_row(label, var, row, width=60):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ent = ttk.Entry(frm, textvariable=var, width=width)
            ent.grid(row=row, column=1, sticky="we", pady=4, columnspan=2)
            return ent

        self.columnconfigure(1, weight=1)
        frm.columnconfigure(1, weight=1)

        self.base_url_var = tk.StringVar(value=self._cfg.get("base_url", ""))
        self.get_users_url_var = tk.StringVar(value=self._cfg.get("get_users_url", ""))
        self.get_timeline_url_var = tk.StringVar(value=self._cfg.get("get_timeline_url", ""))
        self.xsrf_var = tk.StringVar(value=self._cfg.get("headers", {}).get("x-xsrf-token", ""))
        self.cookie_var = tk.StringVar(value=self._cfg.get("cookie", ""))
        self.download_dir_var = tk.StringVar(value=self._cfg.get("download_dir", ""))

        add_row("base_url", self.base_url_var, 0)
        add_row("get_users_url", self.get_users_url_var, 1)
        add_row("get_timeline_url", self.get_timeline_url_var, 2)
        add_row("x-xsrf-token", self.xsrf_var, 3)
        add_row("cookie", self.cookie_var, 4)

        ttk.Label(frm, text="download_dir").grid(row=5, column=0, sticky="w", pady=4)
        dd_row = ttk.Frame(frm)
        dd_row.grid(row=5, column=1, sticky="we", pady=4, columnspan=2)
        self.dd_entry = ttk.Entry(dd_row, textvariable=self.download_dir_var, width=60)
        self.dd_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(dd_row, text="浏览...", command=self._browse_dir).pack(side="left", padx=(6, 0))

        # ---- 底部按钮 ----
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="保存", command=self._save).pack(side="right", padx=(0, 8))

        # 回车保存 / Esc 关闭
        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _browse_dir(self):
        # filedialog requires a valid directory and proper parent; otherwise it may
        # hang when this dialog has grabbed the focus. Expand user symbols and
        # explicitly set *parent* so the dialog behaves correctly on all systems.
        cur = os.path.expanduser(self.download_dir_var.get().strip() or ".")
        d = filedialog.askdirectory(parent=self, initialdir=cur)
        if d:
            self.download_dir_var.set(d)

    def _save(self):
        # 收集基础字段
        new_cfg = copy.deepcopy(self._cfg)
        new_cfg["base_url"] = self.base_url_var.get().strip()
        new_cfg["get_users_url"] = self.get_users_url_var.get().strip()
        new_cfg["get_timeline_url"] = self.get_timeline_url_var.get().strip()
        new_cfg["cookie"] = self.cookie_var.get()
        new_cfg["download_dir"] = self.download_dir_var.get().strip() or "./downloads"
        headers_obj = new_cfg.setdefault("headers", {})
        headers_obj["x-xsrf-token"] = self.xsrf_var.get().strip()

        # 基本校验
        required = ["base_url", "get_users_url", "get_timeline_url"]
        for k in required:
            if not new_cfg.get(k):
                messagebox.showerror("错误", f"{k} 不能为空")
                return

        # 成功：调用回调并关闭
        try:
            self.on_save(new_cfg)
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败：{e}")
            return
        self.destroy()
