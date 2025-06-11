import os
import yaml
import requests
import subprocess
import shutil
from urllib.parse import urljoin


# 加载配置文件
def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


cfg = load_config()

# 公共 headers（含 Cookie 和 x-xsrf-token）
HEADERS = cfg["headers"].copy()
HEADERS["Cookie"] = cfg["cookie"]

# 入口前检查依赖
if shutil.which("ffmpeg") is None:
    print("错误：未找到 ffmpeg。请先安装 ffmpeg 并确保其在系统 PATH 中。")
    exit(1)


# 获取订阅列表
def get_subscription_list():
    resp = requests.get(cfg["base_url"], headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


# 解析订阅列表
def parse_subscription_list(resp_json):
    subs = []
    for item in resp_json.get("data", []):
        subs.append(
            {
                "user_code": item["user_code"],
                "plan_id": item["plan_id"],
            }
        )
    return subs


# 根据 user_code 获取用户信息
def get_user_info_by_code(user_code):
    resp = requests.get(cfg["get_users_url"], headers=HEADERS, params={"user_code": user_code})
    resp.raise_for_status()
    data = resp.json()
    user = data["data"]["user"]
    return {
        "user_code": user["user_code"],
        "username": user["username"],
        "user_id": user["id"],
    }


# 获取时间线
def get_timeline(user_id, page=1, record=12):
    params = {
        "user_id": user_id,
        "sort_order": "new",
        "record": record,
        "page": page,
        "post_type[0]": 1,
    }
    resp = requests.get(cfg["get_timeline_url"], headers=HEADERS, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


# 提取 m3u8 URL
def extract_m3u8_url(post):
    for att in post.get("attachments", []):
        url = att.get("default")
        if url and url.endswith(".m3u8"):
            return url
    return None


# 创建目录
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


# 下载并合并函数
def download_and_merge(m3u8_url, target_dir, output_name):
    ensure_dir(target_dir)

    # 下载 m3u8 文本
    r = requests.get(m3u8_url, headers=HEADERS)
    r.raise_for_status()
    m3u8_text = r.text
    m3u8_filename = os.path.join(target_dir, os.path.basename(m3u8_url))
    with open(m3u8_filename, "w", encoding="utf-8") as f:
        f.write(m3u8_text)

    # 判断 Master Playlist
    lines = [l.strip() for l in m3u8_text.splitlines() if l.strip()]
    if any(l.startswith("#EXT-X-STREAM-INF") for l in lines):
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                sub = lines[i + 1]
                base = m3u8_url.rsplit("/", 1)[0] + "/"
                sub_url = sub if sub.startswith("http") else urljoin(base, sub)
                return download_and_merge(sub_url, target_dir, output_name)

    # 解析 TS 列表
    base = m3u8_url.rsplit("/", 1)[0] + "/"
    ts_urls = [(l if l.startswith("http") else urljoin(base, l)) for l in lines if not l.startswith("#")]

    # 下载 TS 并生成合并列表
    filelist_path = os.path.join(target_dir, "filelist.txt")
    with open(filelist_path, "w", encoding="utf-8") as list_f:
        for idx, ts in enumerate(ts_urls):
            ts_name = f"{idx:04d}.ts"
            ts_path = os.path.join(target_dir, ts_name)
            resp = requests.get(ts, headers=HEADERS, stream=True)
            resp.raise_for_status()
            with open(ts_path, "wb") as ts_f:
                for chunk in resp.iter_content(1024 * 1024):
                    ts_f.write(chunk)
            list_f.write(f"file '{ts_name}'\n")
            print(f"[下载 TS] {ts_name}")

    # 合并 TS
    output_path = os.path.join(target_dir, output_name)
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", filelist_path, "-c", "copy", output_path]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("错误：无法执行 ffmpeg。请确保 ffmpeg 已正确安装并在 PATH 中。")
        exit(1)
    print(f"[合并完成] {output_path}")

    # 清理中间文件
    for fname in os.listdir(target_dir):
        if fname.endswith(".ts") or fname.endswith(".m3u8") or fname == "filelist.txt":
            os.remove(os.path.join(target_dir, fname))
    print(f"[清理] 中间文件已删除")


# 主流程
if __name__ == "__main__":
    subs_resp = get_subscription_list()
    subs = parse_subscription_list(subs_resp)

    for sub in subs:
        info = get_user_info_by_code(sub["user_code"])
        user_dir = os.path.join(cfg["download_dir"], info["user_code"])
        page = 1
        while True:
            timeline = get_timeline(info["user_id"], page=page)
            for post in timeline:
                m3u8 = extract_m3u8_url(post)
                if not m3u8:
                    continue
                ym = post["month"]  # e.g. "2025-06"
                pid = post["post_id"]
                title = post["title"]
                target = os.path.join(user_dir, ym, str(title))
                out_name = f"{title}.mp4"
                print(f"\n== 开始下载 {info['user_code']} {ym} {title} ==")
                if os.path.exists(os.path.join(target, out_name)):
                    print(f"[跳过] {out_name} 已存在")
                    continue
                download_and_merge(m3u8, target, out_name)
            page += 1
            if len(timeline) < cfg["record"]:
                break
