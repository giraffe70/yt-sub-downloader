# utils/subtitle_handler.py

import re
import html
import yt_dlp
import zipfile
import io
import os
import tempfile
from typing import Optional, List, Dict
import streamlit as st
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


def convert_vtt_to_txt(vtt_content: str) -> str:
    if not vtt_content: return ""
    lines = vtt_content.strip().split('\n')
    subtitle_lines = []
    for line in lines:
        line = line.strip()
        line_upper = line.upper()
        if (not line or '-->' in line or re.fullmatch(r'\d+', line) or line_upper.startswith('WEBVTT') or line_upper.startswith('KIND:') or line_upper.startswith('LANGUAGE:')):
            continue
        cleaned_line = html.unescape(re.sub(r'<[^>]+>', '', line))
        subtitle_lines.append(cleaned_line)
    unique_lines = [line for i, line in enumerate(subtitle_lines) if i == 0 or line != subtitle_lines[i-1]]
    return "\n".join(unique_lines)

def convert_vtt_to_srt(vtt_content: str) -> str:
    if not vtt_content: return ""
    # WEBVTT header might not always be present, but cleaning it up is good
    content = re.sub(r'WEBVTT\s*', '', vtt_content).strip()
    # VTT uses '.' for milliseconds, SRT uses ','
    # This regex is safer than a simple replace, targeting only timestamps
    content = re.sub(r'(\d{2}:\d{2}:\d{2})\.(\d{3})', r'\1,\2', content)
    return content

def create_zip_in_memory(files_data: Dict[str, bytes]) -> Optional[bytes]:
    if not files_data: return None
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, content in files_data.items():
                if content:
                    zipf.writestr(filename, content)
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    except Exception as e:
        print(f"Error creating ZIP in memory: {e}")
        return None

# --- 下載函式 ---
def fetch_url_content(url: str, timeout: int = 10) -> Optional[str]:
    """使用 requests 抓取單一 URL 的內容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()  # 如果請求失敗 (如 404, 500)，會拋出異常
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {url}: {e}")
        return None

def download_subtitles_concurrently(lang_to_url_map: Dict[str, str]) -> Dict[str, Optional[str]]:
    """
    使用執行緒池並行下載所有提供的字幕 URL。
    - lang_to_url_map: 一個字典，格式為 { '語言代碼': '字幕VTT檔URL' }
    """
    results = {}
    # 使用 ThreadPoolExecutor 來並行處理網路請求
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 建立 future -> lang 的映射，方便稍後取回結果
        future_to_lang = {executor.submit(fetch_url_content, url): lang for lang, url in lang_to_url_map.items()}
        
        for future in as_completed(future_to_lang):
            lang = future_to_lang[future]
            try:
                content = future.result()
                results[lang] = content
            except Exception as e:
                print(f"Error fetching subtitle for {lang}: {e}")
                results[lang] = None
    return results
    

@st.cache_data(ttl=3600)
def download_subtitles_in_batch(url_unused: str, langs_to_download: List[str], all_sub_info: Dict) -> Dict[str, Optional[str]]:
    """
    批次下載函式
    - langs_to_download: 需要下載的語言列表。
    - all_sub_info: 從 fetch_video_info 獲取的完整字幕資訊字典。
    """
    if not langs_to_download or not all_sub_info:
        return {}

    target_urls = {}
    for lang in langs_to_download:
        if lang in all_sub_info:
            # 找到 vtt 格式的 URL
            for fmt in all_sub_info[lang].get('formats', []):
                if fmt.get('ext') == 'vtt':
                    target_urls[lang] = fmt.get('url')
                    break
    
    if not target_urls:
        return {lang: None for lang in langs_to_download}

    return download_subtitles_concurrently(target_urls)
    
