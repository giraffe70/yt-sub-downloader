# utils/fetch_info.py

import yt_dlp
import streamlit as st
import time

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
                # 使用 download=False 獲取元數據
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
    COMMON_LANGS = ['zh-Hant', 'zh-Hans', 'en', 'ja', 'ko']
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

@st.cache_data(ttl=3600)
def fetch_comments(url: str, top_k: int, sort_by: str, min_likes: int) -> list:
    # 動態計算抓取數量，增加緩衝以避免分頁問題
    # 我們請求比使用者需要的多一點（例如多50則），以確保 yt-dlp 有足夠的資料量可以處理
    # 同時設定一個上限，避免請求過多
    dynamic_fetch_limit = min(top_k + 50, 400)

    ydl_opts = {
        "skip_download": True, 
        "quiet": True, 
        "no_warnings": True, 
        "getcomments": True,
        "ignoreerrors": True,
        # 使用動態計算的抓取數量
        "extractor_args": {"youtube": {"comment_sort": sort_by, "max_comments": {"count": dynamic_fetch_limit}}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 使用 download=True。在 getcomments 模式下，這能更穩定地觸發純元數據提取流程
            info = ydl.extract_info(url, download=True)
            
            # 更安全的檢查，防止因影片資訊不完整而崩潰
            if not info:
                print("Warning: fetch_comments returned no info dict.")
                return []
            raw_comments = info.get('comments')
            if not raw_comments:
                return []
        
        processed_comments = []
        for comment in raw_comments:
            # 增加對 comment 本身的檢查
            if comment and comment.get('like_count', 0) >= min_likes:
                main_comment_data = {
                    'text': comment.get('text'),
                    'author': comment.get('author'),
                    'like_count': comment.get('like_count', 0),
                    'replies': []
                }
                if comment.get('replies'):
                    for reply in comment['replies']:
                        # 增加對 reply 的檢查
                        if reply:
                            main_comment_data['replies'].append({
                                'text': reply.get('text'),
                                'author': reply.get('author'),
                                'like_count': reply.get('like_count', 0),
                            })
                processed_comments.append(main_comment_data)

        if sort_by == 'top':
            processed_comments.sort(key=lambda c: c.get('like_count', 0), reverse=True)
        
        # 最後再根據使用者精確要求的 top_k 數量回傳結果
        return processed_comments[:top_k]
    except Exception as e:
        # 提供更詳細的錯誤日誌
        print(f"An exception occurred in fetch_comments: {type(e).__name__} - {e}")
        # 將錯誤回傳給前端，讓使用者知道發生問題
        raise e