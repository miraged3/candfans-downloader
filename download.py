import os
import sys

import yaml

from api import (
    get_subscription_list,
    parse_subscription_list,
    get_user_info_by_code,
    get_timeline,
)

from config import cfg, check_requirements, load_config

try:
    from downloader import sanitize_filename, download_and_merge
except RuntimeError as e:
    print(f"错误：{e}")
    sys.exit(1)


try:
    load_config()
except FileNotFoundError:
    print("错误：未找到 config.yaml")
    sys.exit(1)
except yaml.YAMLError as e:
    print(f"配置文件格式错误: {e}")
    sys.exit(1)


if __name__ == "__main__":
    if not check_requirements():
        print("\n请先安装缺少的依赖：")
        print("pip install -r requirements.txt")
        sys.exit(1)
    subs_resp = get_subscription_list()
    subs_1 = parse_subscription_list(subs_resp)

    for sub in subs_1:
        info = get_user_info_by_code(sub["user_code"])
        user_dir = os.path.join(cfg["download_dir"], info["user_code"])
        page_1 = 1
        while True:
            timeline = get_timeline(info["user_id"], page=page_1)
            for post_1 in timeline:
                file_type = ''
                attachments = post_1.get("attachments") or []
                if not attachments:
                    continue
                url = attachments[0].get("default")
                if url and url.endswith(".m3u8"):
                    file_type = 'm3u8'
                elif url and url.endswith(".mp4"):
                    file_type = 'mp4'
                else:
                    print(f"链接：{url} 的格式不被支持！")
                    continue
                pid = post_1["post_id"]
                ym = post_1.get("month", "unknown_month")
                title = sanitize_filename(post_1.get("title", "untitled"))
                target = os.path.join(str(user_dir), ym, str(title))
                out_name = f"{title}_{pid}.mp4"
                print(f"\n== 开始下载 {info['user_code']} {ym} {title} ({pid}) ==")
                if os.path.exists(os.path.join(target, out_name)):
                    print(f"[跳过] {out_name} 已存在")
                    continue
                download_and_merge(url, target, out_name, file_type)
            page_1 += 1
            if len(timeline) < 12:
                break
