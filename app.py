# app.py

import streamlit as st
from slugify import slugify
import re
import html

# --- Using correct imports ---
from utils.fetch_info import fetch_video_info, get_available_subtitles, fetch_comments
import utils.subtitle_handler as submod

st.set_page_config(page_title="YouTube Downloader", page_icon="💬", layout="centered")
st.title("💬 YouTube Subtitle & Comment Downloader")

# --- Session State ---
keys_to_init = {
    "url_input": "",
    "info": None,
    "title": "",
    "subtitles": {},
    "selected_langs": set(),
    "select_all_langs": False,
    "selected_formats": ["txt"],
    "select_all_formats": False,
    "processed_results": [],
    "preview_lang": None,
    "comments": [],
    "comments_text_for_download": "",
    "total_comment_count": 0,
}
for key, value in keys_to_init.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Helper Functions ---
def reset_page():
    """Clears all session state values, except for widget-bound keys."""
    widget_keys = ["url_input"]
    for key in keys_to_init.keys():
        if key not in widget_keys:
            st.session_state[key] = keys_to_init[key]
    st.session_state.selected_formats = ["txt"]
    st.session_state.url_input = ""

# 檔名處理函式
def create_safe_filename(title, lang_or_suffix, fmt, is_comment=False):
    """
    Creates a filesystem-safe filename with improved title truncation logic.
    Args:
        title (str): The video title.
        lang_or_suffix (str): The language code (e.g., 'zh-Hant') or a suffix for comments (e.g., 'top_50').
        fmt (str): The file format/extension (e.g., 'txt').
        is_comment (bool): Flag to slightly change the format for comments.
    """
    # 移除不安全的字元，特別是問號
    processed_title = re.sub(r'[\?]', '', title)
    
    # 新的標題截斷邏輯
    # 定義分隔符號
    separators = r'\s*[|:：#—-]\s*'
    
    # 只有當標題長度大於10時才考慮截斷
    if len(processed_title) > 10:
        # 尋找標題後半部分的第一個分隔符號
        mid_point = len(processed_title) // 2
        match = re.search(separators, processed_title[mid_point:])
        
        if match:
            # 如果在後半段找到分隔符號，則從該處截斷
            split_point = mid_point + match.start()
            processed_title = processed_title[:split_point].strip()

    # 使用 slugify 進一步清理標題，使其對檔案系統安全
    safe_title = slugify(processed_title, allow_unicode=True) or "video"
    
    # 獲取上傳日期
    upload_date = st.session_state.info.get("upload_date", "")
    
    # 根據是否為留言，產生不同的檔名格式
    if is_comment:
        return f"{safe_title}_{lang_or_suffix}_com_{upload_date}.{fmt}"
    else:
        return f"{safe_title}_{lang_or_suffix}_{upload_date}.{fmt}"


# 手動重試的處理函式
def retry_single_download(lang, fmt):
    """Handles the logic for retrying a single failed download."""
    try:
        st.toast(f"正在重試 {lang} ({fmt.upper()})...", icon="⏳")
        all_contents = submod.download_subtitles_in_batch(st.session_state.url_input, [lang])
        raw_content = all_contents.get(lang)

        if not raw_content:
            raise ValueError("Retry failed: Empty content received.")

        content_bytes = None
        if fmt == "txt":
            info = st.session_state.info
            title = info.get("title", "Untitled Video")
            upload_date = info.get("upload_date")
            formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if upload_date else "Unknown"
            header = f"【影片標題】：{title}\n【網址】：{st.session_state.url_input}\n\n【發布時間】：{formatted_date}\n【語言】: {lang}\n\n【字幕】：\n"
            plain_text = submod.convert_vtt_to_txt(raw_content)
            full_text = header + plain_text
            content_bytes = full_text.encode('utf-8')
        elif fmt == "srt":
            srt_text = submod.convert_vtt_to_srt(raw_content)
            content_bytes = srt_text.encode('utf-8')
        
        idx_to_update = -1
        for i, item in enumerate(st.session_state.processed_results):
            if item[0] == (lang, fmt):
                idx_to_update = i
                break
        
        if idx_to_update != -1:
            st.session_state.processed_results[idx_to_update] = ((lang, fmt), content_bytes, None)
            st.toast(f"成功重試 {lang} ({fmt.upper()})！", icon="✅")

    except Exception as e:
        st.toast(f"重試 {lang} ({fmt.upper()}) 失敗：{e}", icon="🚨")

# --- UI Layout ---
# Main Form for URL Input
with st.form("parse_form"):
    st.text_input("輸入 YouTube 影片網址", key="url_input")

    col_a, col_b = st.columns([1,1])
    submit_parse = col_a.form_submit_button("解析影片 (Parse Video)", use_container_width=True)
    col_b.form_submit_button("重設 (Reset)", use_container_width=True, on_click=reset_page)

# --- Core Logic: Parsing Video ---
if submit_parse:
    for key in ["info", "title", "subtitles", "processed_results", "comments", "comments_text_for_download", "preview_lang", "total_comment_count"]:
        if key in st.session_state:
            st.session_state[key] = keys_to_init.get(key)

    if st.session_state.url_input.strip():
        with st.spinner("Parsing video..."):
            try:
                full_info = fetch_video_info(st.session_state.url_input.strip())
                st.session_state.info = full_info
                st.session_state.title = full_info.get("title", "Untitled Video")
                st.session_state.subtitles = get_available_subtitles(full_info)
                st.session_state.total_comment_count = full_info.get("comment_count", 0)
            except Exception as e:
                st.error(f"解析影片失敗：\n{e}")
    else:
        st.warning("請輸入網址 (Please enter a Youtube URL.)")

# --- Main Feature Area (Displayed after successful parsing) ---
if st.session_state.info:
    st.success(f"影片標題： {st.session_state.title}")
    st.markdown("---")

    # --- Subtitle Feature Area ---
    st.subheader("字幕功能 (Subtitle Features)")
    if st.session_state.subtitles:
        with st.expander("Click to expand subtitle options", expanded=True):
            st.markdown("##### 1. 選擇字幕語言 (Select Subtitle Languages)")
            def on_toggle_all_langs():
                if st.session_state.select_all_langs:
                    st.session_state.selected_langs = set(st.session_state.subtitles.keys())
                else:
                    st.session_state.selected_langs = set()
            st.checkbox("全選 (Select All)", key="select_all_langs", on_change=on_toggle_all_langs)
            
            sub_keys = sorted(list(st.session_state.subtitles.keys()))
            cols = st.columns(3)
            for i, lang in enumerate(sub_keys):
                meta = st.session_state.subtitles[lang]
                with cols[i % 3]:
                    label = f"{lang} {'(自動)' if meta.get('auto') else ''}"
                    if st.checkbox(label, value=(lang in st.session_state.selected_langs), key=f"chk-{lang}"):
                        st.session_state.selected_langs.add(lang)
                    elif lang in st.session_state.selected_langs:
                        st.session_state.selected_langs.discard(lang)
                        if st.session_state.select_all_langs:
                            st.session_state.select_all_langs = False
            
            st.markdown("---")
            st.markdown("##### 📝 字幕預覽 (Subtitle Preview)")
            selected_langs_list = sorted(list(st.session_state.selected_langs))
            if not selected_langs_list:
                st.info("請至少選擇一種語言以進行預覽 (Please select a language to preview.)")
            else:
                def get_preview_content(_url, _lang):
                    try:
                        content_dict = submod.download_subtitles_in_batch(_url, [_lang])
                        raw_content = content_dict.get(_lang)
                        return submod.convert_vtt_to_txt(raw_content) if raw_content else "Could not load preview content."
                    except Exception as e:
                        return f"載入預覽時發生錯誤：\n{e}"

                st.selectbox("選擇要預覽的語言 (Select language to preview)", options=selected_langs_list, key="preview_lang")
                
                # 使用 st.code 搭配 st.container 建立可複製、固定高度、可滾動的預覽區塊
                if st.session_state.preview_lang:
                    with st.spinner(f"正在載入字幕預覽..."):
                        preview_text = get_preview_content(st.session_state.url_input, st.session_state.preview_lang)
                        
                        # 建立一個固定高度的容器來放置程式碼區塊
                        preview_container = st.container(height=260, border=True)
                        with preview_container:
                            # st.code 提供了一個內建的複製按鈕
                            st.code(preview_text, language=None)

            st.markdown("---")
            st.markdown("##### 2. 選擇輸出格式 (Select Output Formats)")
            AVAILABLE_FORMATS = {"txt": "TXT (純文字)", "srt": "SRT (字幕檔)"}
            st.session_state.selected_formats = st.multiselect(
                "可複選 (You can select multiple formats)",
                options=list(AVAILABLE_FORMATS.keys()),
                default=st.session_state.selected_formats,
                format_func=lambda v: AVAILABLE_FORMATS.get(v, v)
            )

            st.markdown("---")
            st.markdown("##### 3. 下載字幕 (Download Subtitles)")
            if st.button("🚀 開始下載 (Start Download)", type="primary", use_container_width=True):
                st.session_state.processed_results = []
                if not st.session_state.selected_langs or not st.session_state.selected_formats:
                    st.warning("請至少選擇一種語言和一種格式 (Please select at least one language and one format.)")
                else:
                    with st.spinner("Processing subtitles..."):
                        sorted_langs = sorted(list(st.session_state.selected_langs))
                        try:
                            all_contents = submod.download_subtitles_in_batch(st.session_state.url_input, sorted_langs)
                            
                            for lang in sorted_langs:
                                raw_content = all_contents.get(lang)
                                if not raw_content:
                                    for fmt in st.session_state.selected_formats:
                                        st.session_state.processed_results.append(((lang, fmt), None, "處理失敗或內容為空"))
                                    continue
                                for fmt in st.session_state.selected_formats:
                                    content_bytes = None
                                    if fmt == "txt":
                                        info = st.session_state.info
                                        title = info.get("title", "Untitled Video")
                                        upload_date = info.get("upload_date")
                                        formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if upload_date else "Unknown"
                                        header = f"【影片標題】：{title}\n【網址】：{st.session_state.url_input}\n\n【發布時間】：{formatted_date}\n【語言】: {lang}\n\n【字幕】：\n"
                                        plain_text = submod.convert_vtt_to_txt(raw_content)
                                        full_text = header + plain_text
                                        content_bytes = full_text.encode('utf-8')
                                    elif fmt == "srt":
                                        srt_text = submod.convert_vtt_to_srt(raw_content)
                                        content_bytes = srt_text.encode('utf-8')
                                    st.session_state.processed_results.append(((lang, fmt), content_bytes, None))
                        except Exception as e:
                            for lang in sorted_langs:
                                for fmt in st.session_state.selected_formats:
                                    st.session_state.processed_results.append(((lang, fmt), None, str(e)))
            
            if st.session_state.processed_results:
                successful_downloads = [item for item in st.session_state.processed_results if item[1]]
                failed_downloads = [item for item in st.session_state.processed_results if not item[1]]
                
                if len(successful_downloads) > 1:
                    zip_title_base = re.sub(r'[\?]', '', st.session_state.title)
                    zip_safe_title = slugify(zip_title_base, allow_unicode=True) or "video"
                    files_to_zip = {create_safe_filename(st.session_state.title, item[0][0], item[0][1]): item[1] for item in successful_downloads}
                    zip_bytes = submod.create_zip_in_memory(files_to_zip)
                    if zip_bytes:
                        zip_filename = f"{zip_safe_title}_subtitles.zip"
                        st.download_button("📥 Download All (zip)", zip_bytes, zip_filename, "application/zip", type="primary", use_container_width=True)
                
                if successful_downloads:
                    st.write("Download:")
                    cols = st.columns(3)
                    for i, ((lang, fmt), content, _) in enumerate(successful_downloads):
                        with cols[i % 3]:
                            filename = create_safe_filename(st.session_state.title, lang, fmt)
                            st.download_button(f"下載 {lang} ({fmt.upper()})", content, filename, key=f"dlbtn-{lang}-{fmt}", use_container_width=True)
                
                if failed_downloads:
                    st.write("Failed Items:")
                    for item in failed_downloads:
                        (lang, fmt), _, err = item
                        
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            simple_err = str(err).split('\n')[0]
                            if 'HTTP Error 429' in simple_err:
                                simple_err = "請求被阻擋(429)，請稍後重試"
                            st.error(f"❌ {lang} ({fmt.upper()}): {simple_err}", icon="🚨")
                        with col2:
                            st.button("重試", key=f"retry_{lang}_{fmt}", on_click=retry_single_download, args=(lang, fmt), use_container_width=True)

    else:
        st.info("ℹ️ 此影片沒有可用的字幕 (No subtitles are available for this video.)")

    st.markdown("---")

    # --- Comment Feature Area ---
    st.subheader("留言功能 (Comment Features)")
    with st.expander("Click to expand comment options", expanded=True):
        if st.session_state.total_comment_count is not None:
            st.markdown(f"**影片總留言數:** `{st.session_state.total_comment_count:,}`")
        
        #st.markdown("##### 設定篩選條件 (Set Filter Criteria)")
        filter_cols = st.columns(3)
        with filter_cols[0]:
            top_k = st.number_input("抓取數量", min_value=1, max_value=1000, value=50, step=5, key="comment_count", help="要抓取的熱門留言最大數量")
        with filter_cols[1]:
            min_likes = st.number_input("最少讚數", min_value=0, value=1, step=1, key="min_likes_filter", help="只抓取讚數大於或等於此數值的熱門留言")
        with filter_cols[2]:
            sort_by = st.radio("排序方式", options=['top', 'new'], format_func=lambda x: "熱門留言" if x == 'top' else "最新留言", key="comment_sort")
        
        if st.button("🔍 抓取留言 (Fetch Comments)", use_container_width=True):
            st.session_state.comments = []
            st.session_state.comments_text_for_download = ""
            with st.spinner("正在抓取留言(可能需要數秒)..."):
                try:
                    comments_data = fetch_comments(st.session_state.url_input, top_k=top_k, sort_by=sort_by, min_likes=min_likes)
                    st.session_state.comments = comments_data
                    if comments_data:
                        sort_text = "熱門" if sort_by == 'top' else "最新"
                        header_lines = [ f"【影片標題】: {st.session_state.title}", f"【URL】: {st.session_state.url_input}", f"【抓取類型】: {len(comments_data)} 則 {sort_text} 留言\n" ]
                        comment_blocks = []
                        for i, c in enumerate(comments_data):
                            main_comment_line = f"{i+1}. {c['text']}"
                            reply_lines = []
                            if c.get('replies'):
                                for r in c['replies']:
                                    reply_lines.append(f"\t↪️ {r['author']}: {r['text']} (👍{r['like_count']})")
                            full_block = main_comment_line
                            if reply_lines:
                                full_block += "\n" + "\n".join(reply_lines)
                            comment_blocks.append(full_block)

                        st.session_state.comments_text_for_download = "\n".join(header_lines) + f"【{sort_text} 留言】:\n" + "\n\n".join(comment_blocks)
                        st.success(f"成功抓取 {len(comments_data)} 則留言！")
                    else:
                        st.warning("找不到符合條件的留言。")
                except Exception as e:
                    st.error(f"抓取留言時發生錯誤: {e}")

        if st.session_state.comments:
            sort_text_fn = f"{'top' if st.session_state.comment_sort == 'top' else 'newest'}_{len(st.session_state.comments)}"
            comment_filename = create_safe_filename(
                st.session_state.title, 
                lang_or_suffix=sort_text_fn, 
                fmt="txt", 
                is_comment=True
            )
            st.download_button(label=f"📥 Download Comments", data=st.session_state.comments_text_for_download.encode('utf-8'), file_name=comment_filename, mime="text/plain", use_container_width=True, type="primary")
            st.markdown("---")
            st.markdown("##### 留言預覽 (Comment Preview)")

            # 使用 st.container 建立固定高度、可滾動的預覽區塊
            comment_container = st.container(height=400, border=True)
            with comment_container:
                if not st.session_state.comments:
                    st.write("無留言可預覽。")
                else:
                    for comment in st.session_state.comments:
                        like_display = f"👍 {comment['like_count']}"
                        st.info(f"**{comment['author']}** {like_display}\n\n{comment['text']}")
                        if comment['replies']:
                            # 這個內層 container 僅用於排版，非滾動
                            with st.container():
                                for reply in comment['replies']:
                                    reply_like_display = f"👍 {reply['like_count']}"
                                    formatted_reply_text = reply['text'].replace('\n', '\n> ')
                                    st.markdown(f"> ↪️ **{reply['author']}** {reply_like_display}\n>\n> {formatted_reply_text}")


# Initial Welcome Message
if not st.session_state.info:
    st.info("👋 請在上方輸入框貼上 YouTube 影片網址並點擊「解析影片」。\n\nPlease paste a YouTube video URL in the box above and click 'Parse Video'.")