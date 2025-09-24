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

@st.cache_data(ttl=3600)
def download_subtitles_in_batch(url: str, langs: List[str]) -> Dict[str, Optional[str]]:
    if not langs:
        return {}

    results = {lang: None for lang in langs}
    with tempfile.TemporaryDirectory() as temp_dir:
        subtitle_template = os.path.join(temp_dir, '%(id)s.%(lang)s.vtt')
        
        ydl_opts = {
            'writesubtitles': True, 
            'writeautomaticsub': True, 
            'subtitleslangs': langs,
            'subtitlesformat': 'vtt', 
            'skip_download': True, 
            'quiet': True, 
            'no_warnings': True,
            "ignoreerrors": True,
            'outtmpl': {'subtitle': subtitle_template},
            "http_headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }

        # 重試邏輯
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_id = info.get('id')

                if video_id:
                    for lang in langs:
                        for actual_file in os.listdir(temp_dir):
                            if actual_file.startswith(video_id) and lang in actual_file:
                                filepath = os.path.join(temp_dir, actual_file)
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    results[lang] = f.read()
                                break
                return results # 成功後直接返回結果
            
            except Exception as e:
                if 'HTTP Error 429' in str(e) and attempt < max_retries:
                    print(f"Rate limited during download_subtitles. Retrying in 5 seconds... (Attempt {attempt + 1})")
                    # 在重試前，清除暫存資料夾中可能已下載的部分檔案
                    for item in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, item))
                    time.sleep(5)
                    continue # 繼續下一次重試
                else:
                    raise e # 如果不是 429 錯誤，或已達最大重試次數，則拋出錯誤

    return results # 如果重試失敗，返回空的結果


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
    return vtt_content.replace('.', ',', 2).lstrip("WEBVTT\n\n")

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
