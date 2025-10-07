import streamlit as st
from slugify import slugify
import re

from utils.fetch_info import fetch_video_info, get_available_subtitles, fetch_comments
import utils.subtitle_handler as submod


st.set_page_config(page_title="YouTube Downloader", page_icon="💬", layout="centered")
st.title("💬 YouTube 字幕與留言下載器")
st.markdown("🔗 [前往 YouTube](https://www.youtube.com)")

# --- Session State ---
keys_to_init = {
    "url_input": "",
    "info": None,
    "title": "",
    "subtitles": {},
    "selected_langs": set(),
    "selected_formats": ["txt"],
    "processed_results": [],
    "preview_lang": None,
    "comments": [],
    "comments_text_for_download": "",
    "total_comment_count": 0,
    "combined_text_for_download": {},
}
for key, value in keys_to_init.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Helper Functions ---

def reset_page():
    """全面重設頁面狀態至初始值。"""
    # 清除與字幕下載相關的快取
    submod.download_subtitles_in_batch.clear()

    # 恢復初始狀態
    for key, value in keys_to_init.items():
        st.session_state[key] = value

    # 清除動態 widget keys
    widget_keys_to_clear = [
        'select_all_langs_cb', 'min_likes_filter', 'download_all_comments_cb',
        'comment_sort', 'min_reply_likes_filter'
    ]
    for key in list(st.session_state.keys()):
        if key.startswith("chk-") or key in widget_keys_to_clear:
            st.session_state.pop(key, None)

    # 清空網址欄位
    st.session_state.url_input = ""


def create_safe_filename(title, lang_or_suffix, fmt, is_comment=False):
    processed_title = re.sub(r'[\?]', '', title)
    separators = r'\s*[|:：#—-]\s*'
    if len(processed_title) > 10:
        mid_point = len(processed_title) // 2
        match = re.search(separators, processed_title[mid_point:])
        if match:
            split_point = mid_point + match.start()
            processed_title = processed_title[:split_point].strip()
    safe_title = slugify(processed_title, allow_unicode=True) or "video"
    upload_date = st.session_state.info.get("upload_date", "") if st.session_state.info else ""
    if is_comment:
        return f"{safe_title}_{lang_or_suffix}_com_{upload_date}.{fmt}"
    else:
        return f"{safe_title}_{lang_or_suffix}_{upload_date}.{fmt}"


def retry_single_download(lang, fmt):
    try:
        st.toast(f"正在重試 {lang} ({fmt.upper()})...", icon="⏳")
        all_contents = submod.download_subtitles_in_batch(
            st.session_state.url_input,
            [lang],
            st.session_state.subtitles
        )
        raw_content = all_contents.get(lang)
        if not raw_content:
            raise ValueError("Retry failed: Empty content received.")
        content_bytes = None
        if fmt == "txt":
            info = st.session_state.info or {}
            title = info.get("title", "Untitled Video")
            upload_date = info.get("upload_date")
            formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if upload_date else "Unknown"
            header = (
                f"【影片標題】：{title}\n"
                f"【網址】：{st.session_state.url_input}\n\n"
                f"【發布時間】：{formatted_date}\n"
                f"【語言】: {lang}\n\n"
                f"【字幕】：\n"
            )
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


def like_tag_in_paren(count: int) -> str:
    """有讚數才回傳 '(👍N)'，否則回傳空字串。"""
    try:
        c = int(count or 0)
    except Exception:
        c = 0
    return f"(👍{c})" if c > 0 else ""


def like_inline(count: int) -> str:
    """預覽區塊：有讚數才回傳 ' 👍 N'，否則回傳空字串。"""
    try:
        c = int(count or 0)
    except Exception:
        c = 0
    return f" 👍 {c}" if c > 0 else ""


# --- UI Layout ---
with st.form("parse_form"):
    st.text_input("輸入 YouTube 影片網址", key="url_input")
    col_a, col_b = st.columns([1, 1])
    submit_parse = col_a.form_submit_button("解析影片 (Parse Video)", use_container_width=True)
    col_b.form_submit_button("重設 (Reset)", use_container_width=True, on_click=reset_page)

if submit_parse:
    # 清除字幕快取
    submod.download_subtitles_in_batch.clear()

    # 僅重置非 widget 狀態
    reset_keys = [
        "info", "title", "subtitles", "processed_results",
        "comments", "comments_text_for_download", "preview_lang",
        "total_comment_count", "selected_langs"
    ]
    for key in reset_keys:
        if key == "selected_langs":
            st.session_state[key] = set()
        else:
            st.session_state[key] = keys_to_init.get(key, None)

    # 清除動態語言 checkbox 的 widget key
    for k in list(st.session_state.keys()):
        if k.startswith("chk-"):
            st.session_state.pop(k, None)

    if st.session_state.url_input.strip():
        with st.spinner("Parsing video..."):
            try:
                full_info = fetch_video_info(st.session_state.url_input.strip())
                st.session_state.info = full_info
                st.session_state.title = full_info.get("title", "Untitled Video")
                st.session_state.subtitles = get_available_subtitles(full_info)
                st.session_state.total_comment_count = full_info.get("comment_count") or 0
            except Exception as e:
                st.error(f"解析影片失敗：\n{e}")
    else:
        st.warning("請輸入網址 (Please enter a Youtube URL.)")

if st.session_state.info:
    st.success(f"影片標題： {st.session_state.title}")
    st.markdown("---")

    st.subheader("字幕功能")
    if st.session_state.subtitles:
        with st.expander("Click to expand subtitle options", expanded=True):
            st.markdown("##### 1. 選擇字幕語言")

            # Callbacks：只改唯一事實來源 selected_langs，不動任何 widget key
            def handle_select_all():
                is_checked = st.session_state.select_all_langs_cb
                all_langs = st.session_state.subtitles.keys()

                if is_checked:
                    st.session_state.selected_langs = set(all_langs)
                else:
                    st.session_state.selected_langs = set()

                # 同步所有子選項的 UI 狀態
                for lang in all_langs:
                    st.session_state[f"chk-{lang}"] = is_checked

            def handle_single_lang_toggle(lang):
                is_checked = st.session_state[f"chk-{lang}"]
                if is_checked:
                    st.session_state.selected_langs.add(lang)
                else:
                    st.session_state.selected_langs.discard(lang)

                all_langs = set(st.session_state.subtitles.keys())
                if all_langs and st.session_state.selected_langs == all_langs:
                    st.session_state.select_all_langs_cb = True
                else:
                    st.session_state.select_all_langs_cb = False

            all_langs = set(st.session_state.subtitles.keys())

            st.checkbox(
                "全選 (Select All)",
                key='select_all_langs_cb',
                on_change=handle_select_all,
            )

            sub_keys = sorted(list(all_langs))
            cols = st.columns(3)
            for i, lang in enumerate(sub_keys):
                meta = st.session_state.subtitles[lang]
                with cols[i % 3]:
                    label = f"{lang} {'(自動)' if meta.get('auto') else ''}"
                    st.checkbox(
                        label,
                        #value=(lang in st.session_state.selected_langs),
                        key=f"chk-{lang}",
                        on_change=handle_single_lang_toggle,
                        args=(lang,),
                    )

            st.markdown("---")
            st.markdown("##### 📝 字幕預覽")
            selected_langs_list = sorted(list(st.session_state.selected_langs))
            if not selected_langs_list:
                st.info("請至少選擇一種語言以進行預覽")
            else:
                st.selectbox(
                    "選擇字幕語言",
                    options=selected_langs_list,
                    key="preview_lang"
                )

                if st.session_state.preview_lang:
                    with st.spinner("Processing..."):
                        content_dict = submod.download_subtitles_in_batch(
                            st.session_state.url_input,
                            [st.session_state.preview_lang],
                            st.session_state.subtitles
                        )
                        raw_content = content_dict.get(st.session_state.preview_lang)
                        preview_text = submod.convert_vtt_to_txt(raw_content) if raw_content else "無法載入預覽內容。"
                        preview_container = st.container(height=260, border=True)
                        with preview_container:
                            st.code(preview_text, language=None)

            st.markdown("---")
            st.markdown("##### 2. 選擇輸出格式")
            AVAILABLE_FORMATS = {"txt": "TXT (純文字)", "srt": "SRT (字幕檔)"}
            st.session_state.selected_formats = st.multiselect(
                "可複選",
                options=list(AVAILABLE_FORMATS.keys()),
                default=st.session_state.selected_formats,
                format_func=lambda v: AVAILABLE_FORMATS.get(v, v)
            )

            st.markdown("---")
            st.markdown("##### 3. 下載字幕")
            if st.button("🚀 開始下載", type="primary", use_container_width=True):
                st.session_state.processed_results = []
                if not st.session_state.selected_langs or not st.session_state.selected_formats:
                    st.warning("請至少選擇一種語言和一種格式!")
                else:
                    with st.spinner("Processing..."):
                        sorted_langs = sorted(list(st.session_state.selected_langs))
                        try:
                            # 取直接 URL
                            target_subs_info = {
                                lang: st.session_state.subtitles[lang]
                                for lang in sorted_langs
                                if lang in st.session_state.subtitles
                            }

                            lang_to_url_map = {}
                            for lang, meta in target_subs_info.items():
                                for f in meta.get('formats', []):
                                    if f.get('ext') == 'vtt':
                                        lang_to_url_map[lang] = f.get('url')
                                        break

                            # 並行下載
                            all_contents = submod.download_subtitles_concurrently(lang_to_url_map)

                            for lang in sorted_langs:
                                raw_content = all_contents.get(lang)
                                if not raw_content:
                                    for fmt in st.session_state.selected_formats:
                                        st.session_state.processed_results.append(((lang, fmt), None, "處理失敗或內容為空"))
                                    continue
                                for fmt in st.session_state.selected_formats:
                                    content_bytes = None
                                    if fmt == "txt":
                                        info = st.session_state.info or {}
                                        title = info.get("title", "Untitled Video")
                                        upload_date = info.get("upload_date")
                                        description = info.get("description", "無簡介")
                                        formatted_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if upload_date else "Unknown"
                                        header = (
                                            f"【影片標題】：{title}\n"
                                            f"【網址】：{st.session_state.url_input}\n\n"
                                            f"【發布日期】：{formatted_date}\n"
                                            f"【語言】: {lang}\n\n"
                                            f"【簡介】：\n{description}\n\n"
                                            f"【字幕】：\n"
                                        )
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
        st.info("ℹ️ 此影片沒有可用的字幕!")

    st.markdown("---")

    # --- Comment Feature Area ---
    st.subheader("留言功能")

    if st.session_state.total_comment_count is not None:
        if st.session_state.total_comment_count == 0:
            st.info("ℹ️ 此影片目前尚無任何留言!")
        else:
            with st.expander("Click to expand comment options", expanded=True):
                st.markdown(f"**影片留言總數 (含回覆):** `{st.session_state.total_comment_count:,}`")

                filter_cols = st.columns(4)
                
                with filter_cols[0]:
                    st.checkbox(
                        "下載全部留言",
                        key="download_all_comments_cb",
                        value=False,
                        help=f"勾選後將下載全部 {st.session_state.total_comment_count:,} 則留言，並忽略下方的讚數篩選條件。"
                    )

                is_select_all_checked = st.session_state.get('download_all_comments_cb', False)

                with filter_cols[1]:
                    st.number_input(
                        "主留言最少讚數",
                        min_value=0, value=1, step=1, key="min_likes_filter",
                        help="只抓取讚數大於或等於此數值的主留言",
                        disabled=is_select_all_checked
                    )
                with filter_cols[2]:
                    st.number_input(
                        "回覆最少讚數",
                        min_value=0, value=1, step=1, key="min_reply_likes_filter",
                        help="只抓取讚數大於或等於此數值的回覆留言",
                        disabled=is_select_all_checked
                    )
                with filter_cols[3]:
                    st.radio("排序方式", options=['top', 'new'], format_func=lambda x: "熱門留言" if x == 'top' else "最新留言", key="comment_sort")

                if st.button("🔍 開始擷取留言", use_container_width=True):
                    st.session_state.comments = []
                    st.session_state.comments_text_for_download = ""
                    with st.spinner("正在擷取留言(可能需要數秒)..."):
                        try:
                            fetch_comments.clear()

                            limit = st.session_state.total_comment_count
                            
                            if is_select_all_checked:
                                likes_filter = 0
                                reply_likes_filter = 0
                                st.toast(f"模式：下載全部留言")
                            else:
                                likes_filter = st.session_state.min_likes_filter
                                reply_likes_filter = st.session_state.min_reply_likes_filter
                                st.toast(f"模式：根據讚數篩選留言")

                            comments_data = fetch_comments(
                                st.session_state.url_input,
                                top_k=limit,
                                sort_by=st.session_state.comment_sort,
                                min_likes=likes_filter,
                                min_reply_likes=reply_likes_filter
                            )
                            
                            st.session_state.comments = comments_data

                            if comments_data:
                                sort_text = "熱門" if st.session_state.comment_sort == 'top' else "最新"
                                header_lines = [
                                    f"【影片標題】: {st.session_state.title}",
                                    f"【URL】: {st.session_state.url_input}"
                                ]
                                comment_blocks = []
                                for i, c in enumerate(comments_data):
                                    likes = int(c.get('like_count', 0) or 0)
                                    like_paren = like_tag_in_paren(likes)
                                    main_comment_line = f"{i+1}{like_paren}. {c['text']}"

                                    reply_lines_formatted = []
                                    if c.get('replies'):
                                        sorted_replies = sorted(c['replies'], key=lambda r: r.get('like_count', 0), reverse=True)
                                        for j, r in enumerate(sorted_replies):
                                            reply_likes = int(r.get('like_count', 0) or 0)
                                            reply_like_paren = like_tag_in_paren(reply_likes)
                                            reply_lines_formatted.append(f"    - {r['author']} 回覆{reply_like_paren}：{r['text']}")
                                            
                                    full_block = main_comment_line
                                    if reply_lines_formatted:
                                        full_block += "\n" + "\n".join(reply_lines_formatted)
                                    comment_blocks.append(full_block)

                                st.session_state.comments_text_for_download = "\n".join(header_lines) + f"【{sort_text} 留言】:\n" + "\n\n".join(comment_blocks)
                                st.success(f"成功擷取 {len(comments_data)} 則留言！")
                            else:
                                st.warning("找不到符合篩選條件的留言。")
                        except Exception as e:
                            st.error(f"擷取留言時發生錯誤: {e}")

                if st.session_state.comments:
                    # --- 合併字幕與留言 ---
                    st.session_state.combined_text_for_download = {}
                    if st.session_state.selected_langs and "txt" in st.session_state.selected_formats:
                        processed_txt_subs = {
                            item[0][0]: item[1].decode('utf-8')
                            for item in st.session_state.processed_results
                            if item[1] and item[0][1] == 'txt'
                        }

                        if processed_txt_subs:
                            full_comment_text = st.session_state.comments_text_for_download
                            comment_header_pattern = re.search(r"【.*?留言】:\n", full_comment_text)

                            if comment_header_pattern:
                                comments_start_index = comment_header_pattern.end()
                                comments_only_text = full_comment_text[comments_start_index:]
                            else:
                                comments_only_text = full_comment_text

                            for lang, sub_content in processed_txt_subs.items():
                                combined_content = f"{sub_content}\n\n---\n【留言】：\n{comments_only_text}"
                                st.session_state.combined_text_for_download[lang] = combined_content.encode('utf-8')

                    # 下載按鈕
                    dl_col_1, dl_col_2 = st.columns(2)

                    with dl_col_1:
                        sort_text_fn = f"{'top' if st.session_state.comment_sort == 'top' else 'newest'}_{len(st.session_state.comments)}"
                        comment_filename = create_safe_filename(st.session_state.title, lang_or_suffix=sort_text_fn, fmt="txt", is_comment=True)
                        st.download_button(
                            label="📥 下載留言",
                            data=st.session_state.comments_text_for_download.encode('utf-8'),
                            file_name=comment_filename,
                            mime="text/plain",
                            use_container_width=True,
                        )

                    with dl_col_2:
                        if st.session_state.combined_text_for_download:
                            first_lang = list(st.session_state.combined_text_for_download.keys())[0]
                            combined_data = st.session_state.combined_text_for_download[first_lang]

                            combined_filename = create_safe_filename(st.session_state.title, lang_or_suffix=f"{first_lang}_full", fmt="txt")
                            st.download_button(
                                label="📜 下載字幕與留言",
                                data=combined_data,
                                file_name=combined_filename,
                                mime="text/plain",
                                use_container_width=True,
                                type="primary"
                            )

                    st.markdown("---")

                    # 預覽
                    st.markdown("##### 留言預覽")
                    comment_container = st.container(height=400, border=True)
                    with comment_container:
                        if not st.session_state.comments:
                            st.write("無留言可預覽。")
                        else:
                            for comment in st.session_state.comments:
                                like_display = like_inline(comment.get('like_count', 0))
                                st.info(f"**{comment['author']}**{like_display}\n\n{comment['text']}")

                                if comment.get('replies'):
                                    _, replies_col = st.columns([0.05, 0.95])
                                    with replies_col:
                                        for reply in comment['replies']:
                                            reply_like_display = like_inline(reply.get('like_count', 0))
                                            formatted_reply_text = reply['text'].replace('\n', '\n> ')
                                            st.markdown(f"""
                                                > ↪️ **{reply['author']}**{reply_like_display}
                                                >
                                                > {formatted_reply_text}
                                                """)
                            st.markdown("---")

if not st.session_state.info:
    st.info("👋 請在上方輸入框貼上 YouTube 影片網址並點擊「解析影片」。\n\nPlease paste a YouTube video URL in the box above and click 'Parse Video'.")
