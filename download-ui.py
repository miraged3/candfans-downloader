# app_gui.py
# 基于你现有脚本改造：提供GUI选择账号与帖子后再下载
import copy
import os
import threading
import queue
import sys

import yaml

from api import (
    get_subscription_list,
    parse_subscription_list,
    get_user_info_by_code,
    get_timeline,
)

from config import (
    cfg,
    check_requirements,
    load_config,
    refresh_headers_from_cfg,
    save_config,
)

try:
    from downloader import sanitize_filename, download_and_merge
except RuntimeError as e:
    print(f"错误：{e}")
    sys.exit(1)

# === GUI ===
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from tkinter.scrolledtext import ScrolledText


# ----------------- 你的原有逻辑（少量改造以便插入GUI） -----------------

try:
    load_config()
except FileNotFoundError:
    print("错误：未找到 config.yaml")
    sys.exit(1)
except yaml.YAMLError as e:
    print(f"配置文件格式错误: {e}")
    sys.exit(1)




# ----------------- GUI 应用 -----------------

class DownloaderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CandFans Downloader - GUI")
        self.geometry("1100x700")

        # 数据
        self.accounts = []  # [{'user_code','username','user_id'}...]
        self.posts = []  # [(acc_dict, post_dict, url_type, url), ...] 当前展示
        self.all_posts_raw = {}  # user_code -> [post_dict...]
        self.log_queue = queue.Queue()
        self.downloading = False
        self.pause_event = threading.Event()
        self.pause_event.set()  # 初始为“运行态”
        self.cancel_event = threading.Event()
        self.current_proc = None  # 记录当前 ffmpeg 进程（Popen），取消时终止

        # UI
        self._build_ui()

        # 定时器：刷日志
        self.after(100, self._flush_logs)

    # ---------- UI ----------
    def _build_ui(self):
        # 顶部操作区
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        self.btn_config = ttk.Button(top, text="配置", command=self.open_config)
        self.btn_config.pack(side="right")

        self.btn_load_accounts = ttk.Button(top, text="加载账号列表", command=self.on_load_accounts)
        self.btn_load_accounts.pack(side="left")

        ttk.Label(top, text="每账号页数:").pack(side="left", padx=(12, 4))
        self.pages_var = tk.IntVar(value=3)
        self.pages_spin = ttk.Spinbox(top, from_=1, to=999, textvariable=self.pages_var, width=5)
        self.pages_spin.pack(side="left")

        self.all_pages_var = tk.BooleanVar(value=False)
        self.chk_all_pages = ttk.Checkbutton(top, text="抓取全部页", variable=self.all_pages_var)
        self.chk_all_pages.pack(side="left", padx=(8, 0))

        ttk.Label(top, text="关键字:").pack(side="left", padx=(12, 4))
        self.keyword_var = tk.StringVar()
        self.keyword_entry = ttk.Entry(top, textvariable=self.keyword_var, width=18)
        self.keyword_entry.pack(side="left")

        ttk.Label(top, text="月份:").pack(side="left", padx=(12, 4))
        self.month_var = tk.StringVar(value="全部")
        self.month_combo = ttk.Combobox(top, textvariable=self.month_var, width=12, state="readonly", values=["全部"])
        self.month_combo.pack(side="left")

        ttk.Label(top, text="类型:").pack(side="left", padx=(12, 4))
        self.type_var = tk.StringVar(value="全部")
        self.type_combo = ttk.Combobox(top, textvariable=self.type_var, width=8, state="readonly",
                                       values=["全部", "mp4", "m3u8"])
        self.type_combo.pack(side="left")

        self.btn_fetch_posts = ttk.Button(top, text="拉取帖子", command=self.on_fetch_posts)
        self.btn_fetch_posts.pack(side="left", padx=(12, 0))

        self.btn_apply_filter = ttk.Button(top, text="筛选", command=self.apply_filter)
        self.btn_apply_filter.pack(side="left", padx=(8, 0))

        # 中部：左右布局
        mid = ttk.Panedwindow(self, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=10, pady=8)

        # 左：账号列表
        left = ttk.Labelframe(mid, text="账号")
        mid.add(left, weight=1)
        self.acc_list = tk.Listbox(left, selectmode="extended")
        self.acc_list.pack(fill="both", expand=True, padx=8, pady=8)

        # 右：帖子表
        right = ttk.Labelframe(mid, text="帖子（按住Ctrl/Shift多选）")
        mid.add(right, weight=3)

        cols = ("account", "month", "title", "type", "post_id")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("account", text="账号")
        self.tree.heading("month", text="月份")
        self.tree.heading("title", text="标题")
        self.tree.heading("type", text="类型")
        self.tree.heading("post_id", text="PostID")
        self.tree.column("account", width=160, anchor="w")
        self.tree.column("month", width=100, anchor="w")
        self.tree.column("title", width=520, anchor="w")
        self.tree.column("type", width=60, anchor="center")
        self.tree.column("post_id", width=120, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        btns = ttk.Frame(right)
        btns.pack(fill="x", padx=8, pady=8)
        ttk.Button(btns, text="全选可见", command=self.select_all_visible).pack(side="left")
        ttk.Button(btns, text="清空选择", command=self.clear_selection).pack(side="left", padx=(8, 0))
        self.btn_download = ttk.Button(btns, text="开始下载", command=self.on_download)
        self.btn_download.pack(side="right")
        self.btn_pause = ttk.Button(btns, text="暂停", command=self.on_pause_resume, state="disabled")
        self.btn_pause.pack(side="right", padx=(8, 0))

        self.btn_cancel = ttk.Button(btns, text="取消", command=self.on_cancel, state="disabled")
        self.btn_cancel.pack(side="right", padx=(8, 0))

        # 底部日志
        logf = ttk.Labelframe(self, text="日志")
        logf.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log_text = tk.Text(logf, height=10)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

    # ---------- 日志 ----------
    def _log(self, msg: str):
        self.log_queue.put(str(msg))

    def _flush_logs(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(120, self._flush_logs)

    def open_config(self):
        # 正在下载时允许查看/修改，但提示更稳妥
        if self.downloading:
            messagebox.showinfo("提示", "当前有下载任务，修改配置可能影响后续请求。建议暂停/取消后再修改。")
        # 打开弹窗
        ConfigDialog(self, cfg, on_save=self.on_config_saved)

    def on_config_saved(self, new_cfg: dict):
        """弹窗保存后更新配置并落盘"""
        save_config(new_cfg)  # 写回 config.yaml 并刷新头部
        self._log("[配置] 已保存并生效。")

    # ---------- 事件 ----------
    def on_load_accounts(self):
        def worker():
            try:
                self._log("正在加载账号列表...")
                subs_resp = get_subscription_list()
                subs = parse_subscription_list(subs_resp)
                accounts = []
                for sub in subs:
                    info = get_user_info_by_code(sub["user_code"])
                    accounts.append(info)
                self.accounts = accounts
                self._log(f"加载完成：{len(accounts)} 个账号")
                self._refresh_account_listbox()
            except Exception as e:
                self._log(f"[错误] 加载账号失败：{e}")
                messagebox.showerror("错误", f"加载账号失败：{e}")

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_account_listbox(self):
        self.acc_list.delete(0, "end")
        for a in self.accounts:
            self.acc_list.insert("end", f"{a['username']} ({a['user_code']})")

    def on_fetch_posts(self):
        sel_indices = self.acc_list.curselection()
        if not sel_indices:
            messagebox.showinfo("提示", "请先选择至少一个账号")
            return

        selected_accounts = [self.accounts[i] for i in sel_indices]
        pages = None if self.all_pages_var.get() else int(self.pages_var.get())

        def worker():
            try:
                months_set = set()
                total_count = 0
                self.all_posts_raw.clear()
                self._log("开始拉取帖子...")

                for acc in selected_accounts:
                    user_posts = []
                    page = 1
                    fetched = 0
                    while True:
                        tl = get_timeline(acc["user_id"], page=page)
                        if not tl:
                            break
                        user_posts.extend(tl)
                        fetched += 1
                        self._log(f"[{acc['username']}] 已拉取第 {page} 页，共 {len(tl)} 条")
                        if pages and fetched >= pages:
                            break
                        if len(tl) < 12:
                            break
                        page += 1

                    self.all_posts_raw[acc["user_code"]] = user_posts
                    total_count += len(user_posts)
                    for p in user_posts:
                        months_set.add(p.get("month", "unknown_month"))

                # 更新月份筛选
                months = sorted(months_set)
                self.month_combo["values"] = ["全部"] + months
                self.month_var.set("全部")

                self._log(f"拉取完成，共 {total_count} 条。正在应用当前筛选...")
                self.apply_filter()
            except Exception as e:
                self._log(f"[错误] 拉取帖子失败：{e}")
                messagebox.showerror("错误", f"拉取帖子失败：{e}")

        threading.Thread(target=worker, daemon=True).start()

    def apply_filter(self):
        # 根据 keyword / month / type 对 self.all_posts_raw 过滤，填充到 tree
        keyword = self.keyword_var.get().strip().lower()
        month_need = self.month_var.get()
        type_need = self.type_var.get()

        # 清空现有
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.posts = []

        def first_attachment_type_url(post):
            attachments = post.get("attachments") or []
            if not attachments:
                return None, None
            url = attachments[0].get("default")
            if not url:
                return None, None
            if url.endswith(".m3u8"):
                return "m3u8", url
            if url.endswith(".mp4"):
                return "mp4", url
            return None, url

        for acc in self.accounts:
            posts_list = self.all_posts_raw.get(acc["user_code"], [])
            for p in posts_list:
                m = p.get("month", "unknown_month")
                title = sanitize_filename(p.get("title", "untitled"))
                ptype, url = first_attachment_type_url(p)

                # 类型过滤：如果没附件/不支持，跳过
                if ptype is None:
                    continue

                if month_need != "全部" and m != month_need:
                    continue
                if keyword and keyword not in title.lower():
                    continue
                if type_need != "全部" and ptype != type_need:
                    continue

                self.posts.append((acc, p, ptype, url))
                self.tree.insert(
                    "", "end",
                    values=(f"{acc['username']}({acc['user_code']})", m, title, ptype, str(p["post_id"]))
                )

        self._log(f"筛选后可下载：{len(self.posts)} 条")

    def select_all_visible(self):
        # 全选 TreeView 中的所有可见行
        self.tree.selection_set(self.tree.get_children())

    def clear_selection(self):
        self.tree.selection_remove(self.tree.get_children())

    def on_download(self):
        if self.downloading:
            messagebox.showinfo("提示", "当前正在下载，请稍候完成后再操作。")
            return

        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请在帖子表格中选择要下载的行。")
            return

        # 根据选择的行还原 (acc, post, ptype, url)
        selected_jobs = []
        rows = list(self.tree.get_children())
        for iid in sel:
            idx = rows.index(iid)
            if 0 <= idx < len(self.posts):
                selected_jobs.append(self.posts[idx])

        if not selected_jobs:
            messagebox.showinfo("提示", "未解析到有效的选择。")
            return

        def worker():
            self.downloading = True
            self.btn_download.config(state="disabled")
            self.cancel_event.clear()
            self.pause_event.set()
            self.btn_pause.config(state="normal", text="暂停")
            self.btn_cancel.config(state="normal")

            try:
                for acc, post_1, file_type, url in selected_jobs:
                    if self.cancel_event.is_set():
                        self._log("[取消] 用户取消，停止后续任务。")
                        break

                    pid = post_1["post_id"]
                    ym = post_1.get("month", "unknown_month")
                    title = sanitize_filename(post_1.get("title", "untitled"))
                    user_dir = os.path.join(cfg["download_dir"], acc["user_code"])
                    target = os.path.join(str(user_dir), ym, str(title))
                    out_name = f"{title}_{pid}.mp4"

                    self._log(f"\n== 开始下载 {acc['user_code']} {ym} {title} ({pid}) ==")
                    if os.path.exists(os.path.join(target, out_name)):
                        self._log(f"[跳过] {out_name} 已存在")
                        continue

                    try:
                        download_and_merge(
                            url, target, out_name, file_type,
                            log=self._log,
                            pause_event=self.pause_event,
                            cancel_event=self.cancel_event,
                            on_ffmpeg=lambda p: setattr(self, "current_proc", p)
                        )

                    except Exception as e:
                        self._log(f"[错误] {title}({pid}) 下载失败：{e}")
                self._log("\n全部任务结束。")
            finally:
                self.downloading = False
                self.current_proc = None
                self.btn_download.config(state="normal")
                self.btn_pause.config(state="disabled", text="暂停")
                self.btn_cancel.config(state="disabled")
                # 若外部还处于暂停态，恢复到运行态，避免下次直接卡住
                self.pause_event.set()
                self.cancel_event.clear()

        threading.Thread(target=worker, daemon=True).start()

    def on_pause_resume(self):
        if not self.downloading:
            return
        # 运行态 -> 暂停
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.config(text="继续")
            self._log("[状态] 已暂停")
        else:
            # 暂停态 -> 继续
            self.pause_event.set()
            self.btn_pause.config(text="暂停")
            self._log("[状态] 已继续")

    def on_cancel(self):
        if not self.downloading and self.current_proc is None:
            return
        self.cancel_event.set()
        self._log("[状态] 正在取消当前任务...")
        # 如果 ffmpeg 正在运行，尽快终止
        if self.current_proc:
            try:
                self.current_proc.terminate()
            except Exception:
                pass


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
        self.cookie_var = tk.StringVar(value=self._cfg.get("cookie", ""))
        self.download_dir_var = tk.StringVar(value=self._cfg.get("download_dir", ""))

        add_row("base_url", self.base_url_var, 0)
        add_row("get_users_url", self.get_users_url_var, 1)
        add_row("get_timeline_url", self.get_timeline_url_var, 2)
        add_row("cookie", self.cookie_var, 3)

        ttk.Label(frm, text="download_dir").grid(row=4, column=0, sticky="w", pady=4)
        dd_row = ttk.Frame(frm)
        dd_row.grid(row=4, column=1, sticky="we", pady=4, columnspan=2)
        self.dd_entry = ttk.Entry(dd_row, textvariable=self.download_dir_var, width=60)
        self.dd_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(dd_row, text="浏览...", command=self._browse_dir).pack(side="left", padx=(6, 0))

        # ---- headers（YAML）----
        ttk.Label(frm, text="headers (YAML 格式的字典)").grid(row=5, column=0, sticky="nw", pady=(10, 4))
        self.headers_text = ScrolledText(frm, height=10)
        self.headers_text.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=(10, 4))
        headers_yaml = yaml.safe_dump(self._cfg.get("headers", {}) or {}, allow_unicode=True, sort_keys=False)
        self.headers_text.insert("1.0", headers_yaml)

        frm.rowconfigure(5, weight=1)

        # ---- 底部按钮 ----
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="保存", command=self._save).pack(side="right", padx=(0, 8))

        # 回车保存 / Esc 关闭
        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir_var.get() or ".")
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

        # 解析 headers YAML
        try:
            headers_obj = yaml.safe_load(self.headers_text.get("1.0", "end")) or {}
            if not isinstance(headers_obj, dict):
                raise ValueError("headers 需要是一个字典")
            new_cfg["headers"] = headers_obj
        except Exception as e:
            messagebox.showerror("错误", f"解析 headers 失败：{e}")
            return

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


# ----------------- 入口 -----------------
def main():
    if not check_requirements():
        print("\n请先安装缺少的依赖：")
        print("pip install -r requirements.txt")
        sys.exit(1)

    app = DownloaderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
