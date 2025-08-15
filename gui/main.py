import os
import threading
import queue

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from api import (
    get_subscription_list,
    parse_subscription_list,
    get_user_info_by_code,
    get_timeline,
)

from config import (
    cfg,
    save_config,
)

from downloader import sanitize_filename, download_and_merge

from .config_dialog import ConfigDialog


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
                for user in subs:
                    accounts.append({
                        "username": user["name"],
                        "user_code": user["code"],
                        "user_id": user["id"],
                    })
                self.accounts = accounts
                self._log(f"加载成功，共 {len(accounts)} 个账号")
            except Exception as e:
                self._log(f"[错误] 加载账号列表失败：{e}")
                return
            finally:
                self.btn_load_accounts.config(state="normal")

            # 刷新 UI
            self.acc_list.delete(0, "end")
            for acc in accounts:
                self.acc_list.insert("end", f"{acc['username']} ({acc['user_code']})")

        self.btn_load_accounts.config(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    def on_fetch_posts(self):
        selected_indices = self.acc_list.curselection()
        if not selected_indices:
            messagebox.showerror("错误", "请先选择账号")
            return
        selected_accounts = [self.accounts[i] for i in selected_indices]

        def worker():
            try:
                self.posts.clear()
                self.all_posts_raw.clear()
                max_pages = None if self.all_pages_var.get() else self.pages_var.get()
                keyword = self.keyword_var.get().strip()
                filter_type = self.type_var.get()
                if filter_type == "全部":
                    filter_type = None
                for acc in selected_accounts:
                    self._log(f"加载账号 {acc['username']} 的帖子...")
                    posts = []
                    page = 1
                    while True:
                        tl = get_timeline(acc["user_id"], page=page)
                        posts.extend(tl["list"])
                        if max_pages and page >= max_pages:
                            break
                        if not tl["has_more"]:
                            break
                        page += 1
                    self.all_posts_raw[acc["user_code"]] = posts
                    for post in posts:
                        urls = []
                        for media in post.get("medias", []):
                            url = media.get("source_url")
                            if not url:
                                continue
                            if filter_type and not url.endswith(filter_type):
                                continue
                            urls.append(url)
                        if keyword and keyword not in post.get("title", ""):
                            continue
                        for url in urls:
                            url_type = "m3u8" if url.endswith(".m3u8") else "mp4"
                            month = post.get("month") or ""
                            self.posts.append((acc, post, url_type, url))
                self._log(f"拉取完毕，共 {len(self.posts)} 条")
            except Exception as e:
                self._log(f"[错误] 拉取帖子失败：{e}")
                return
            finally:
                self.btn_fetch_posts.config(state="normal")

            self.apply_filter()

        self.btn_fetch_posts.config(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    def apply_filter(self):
        # 清空表格
        for row in self.tree.get_children():
            self.tree.delete(row)

        month_filter = self.month_var.get()
        keyword = self.keyword_var.get().strip()
        filter_type = self.type_var.get()
        if filter_type == "全部":
            filter_type = None

        # 重新填充
        months = set()
        for acc, post, url_type, url in self.posts:
            if month_filter != "全部" and post.get("month") != month_filter:
                continue
            if keyword and keyword not in post.get("title", ""):
                continue
            if filter_type and url_type != filter_type:
                continue
            months.add(post.get("month"))
            self.tree.insert("", "end", values=(acc["username"], post.get("month"), post.get("title"), url_type, post.get("post_id")))

        months = sorted(m for m in months if m)
        self.month_combo.config(values=["全部"] + months)
        if month_filter not in months:
            self.month_var.set("全部")

    def select_all_visible(self):
        self.tree.selection_set(self.tree.get_children())

    def clear_selection(self):
        self.tree.selection_clear(self.tree.get_children())

    def on_download(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showerror("错误", "请先选择要下载的项目")
            return

        tasks = []
        for item in selected_items:
            vals = self.tree.item(item, "values")
            acc_name, month, title, url_type, post_id = vals
            acc = next(a for a in self.accounts if a["username"] == acc_name)
            post = next(p for p in self.all_posts_raw[acc["user_code"]] if str(p.get("post_id")) == post_id)
            tasks.append((acc, post, url_type, title))

        self.downloading = True
        self.btn_download.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_cancel.config(state="normal")

        self.cancel_event.clear()
        threading.Thread(target=self._download_worker, args=(tasks,), daemon=True).start()

    def _download_worker(self, tasks):
        for acc, post, url_type, title in tasks:
            if self.cancel_event.is_set():
                self._log("[状态] 已取消")
                break

            self._log(f"[下载] {acc['username']} / {title}")
            medias = post.get("medias", [])
            urls = [m.get("source_url") for m in medias if m.get("source_url")]
            for url in urls:
                if url.endswith(".m3u8"):
                    self._download_m3u8(url, acc, title)
                else:
                    self._download_mp4(url, acc, title)

        self._log("[状态] 下载完成")
        self.downloading = False
        self.btn_download.config(state="normal")
        self.btn_pause.config(state="disabled", text="暂停")
        self.btn_cancel.config(state="disabled")

    def _download_mp4(self, url, acc, title):
        # 标准 mp4 下载
        try:
            download_and_merge(url, acc["username"], title)
            self._log("    完成")
        except Exception as e:
            self._log(f"    [失败] {e}")

    def _download_m3u8(self, url, acc, title):
        # m3u8 下载
        try:
            download_and_merge(url, acc["username"], title)
            self._log("    完成")
        except Exception as e:
            self._log(f"    [失败] {e}")

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
