# utils/fetch_info.py

import yt_dlp
import streamlit as st
import time
import re
from collections import defaultdict

def fetch_video_info(url: str) -> dict:
    """Fetches comprehensive video information using yt-dlp."""
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "http_headers": {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    }
    
    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Failed to fetch video info, yt-dlp returned None. The video might be private, deleted, or region-locked.")
            return info
        except Exception as e:
            if 'HTTP Error 429' in str(e) and attempt < max_retries:
                print(f"Rate limited during fetch_info. Retrying in 5 seconds... (Attempt {attempt + 1})")
                time.sleep(5)
                continue
            else:
                raise e

def get_available_subtitles(info: dict) -> dict:
    if not info: return {}
    COMMON_LANGS = ['zh-Hant', 'zh-Hans', 'en']
    subtitles = {}
    if "subtitles" in info and isinstance(info.get("subtitles"), dict):
        for lang, subs in info["subtitles"].items():
            subtitles[lang] = {"name": lang, "auto": False, "formats": subs}
    if "automatic_captions" in info and isinstance(info.get("automatic_captions"), dict):
        added_common_auto_langs = set()
        for lang, subs in info["automatic_captions"].items():
            for common_lang_prefix in COMMON_LANGS:
                if lang.startswith(common_lang_prefix):
                    if common_lang_prefix not in added_common_auto_langs and lang not in subtitles:
                        subtitles[lang] = {"name": lang, "auto": True, "formats": subs}
                        added_common_auto_langs.add(common_lang_prefix)
                    break
    return subtitles

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_comments(url: str, top_k: int, sort_by: str, min_likes: int, min_reply_likes: int) -> list:
    """
    使用 yt-dlp 擷取留言並進行格式化。
    主留言: {cid, author, text, like_count, replies: [ ... ]}
    回覆: {cid, parent_cid, author, text, like_count}
    """
    
    ydl_opts = {
        'getcomments': True,
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': f'comment_sort={sort_by}&max_comments={top_k + 50}'
        }
    }

    all_comments_raw = []
    try:
        # 使用 yt-dlp 一次性抓取所有留言資訊
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'comments' in info and isinstance(info['comments'], list):
                all_comments_raw = info['comments']
            else:
                return []  # 找不到留言或影片不允許留言
    except Exception as e:
        st.error(f"yt-dlp 抓取留言時發生錯誤: {e}")
        return []

    potential_roots = []
    replies_map = defaultdict(list)

    # 將 yt-dlp 的原始格式轉換為我們需要的內部格式
    def _mk_root(c):
        return {
            "cid": c.get('id', ''),
            "author": c.get('author', 'Unknown'),
            "text": c.get('text', ''),
            "like_count": int(c.get('like_count', 0)),
            "replies": []
        }

    def _mk_reply(c, parent_cid):
        return {
            "cid": c.get('id', ''),
            "parent_cid": parent_cid,
            "author": c.get('author', 'Unknown'),
            "text": c.get('text', ''),
            "like_count": int(c.get('like_count', 0)),
        }

    # 第一次遍歷：將所有留言分類為主留言和回覆
    for c in all_comments_raw:
        if not isinstance(c, dict):
            continue
        
        parent_id = c.get('parent')
        # 如果 parent ID 是 'root' 或不存在，視為主留言
        if not parent_id or parent_id == 'root':
            like_count = int(c.get('like_count', 0))
            if like_count >= min_likes:
                potential_roots.append(_mk_root(c))
        # 否則視為回覆
        else:
            reply_like_count = int(c.get('like_count', 0))
            if reply_like_count >= min_reply_likes:
                replies_map[parent_id].append(_mk_reply(c, parent_id))
    
    # 根據 UI 選擇的排序方式對主留言進行排序
    if sort_by == 'top':
        potential_roots.sort(key=lambda r: r.get('like_count', 0), reverse=True)
    
    # 根據 UI 選擇的數量，篩選出最終的主留言
    final_roots = potential_roots[:top_k]

    # 第二次遍歷：將回覆掛載到最終的主留言上
    for root in final_roots:
        cid = root.get("cid")
        if cid and cid in replies_map:
            root["replies"] = replies_map[cid]

    return final_roots
