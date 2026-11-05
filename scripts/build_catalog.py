#!/usr/bin/env python3
"""Build the offline catalog from captured course data and verified local manifests.

Never republishes signed media URLs or play credentials. Missing videos remain
pending unless a final fallback status is explicitly supplied.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
INTRO_HEADINGS = [
    '1. 母语水平：人类习得语言的原理', '2. 母语和第二语言的差异：无痛与有痛',
    '3. 兴趣：持续性和实践性', '4. 对父母的挑战', '5. 听说读写的顺序',
    '6. 听', '7. 说', '8. 读', '9. 写', '10. 环境的营造', '11. 许闻的书房',
    '12. 许瞧的闺房', '13. 绘本的使用', '14. 大童的英语追赶',
    '15. 成年人（父母）的最后一搏', '16. -',
]
STATUS_NAMES = {'downloaded': '完整保存', 'partial': '部分保存', 'pending': '待下载', 'failed': '下载未完成', 'locked': '需访问权限'}


def read_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def unsigned_url(value):
    parts = urlsplit(str(value or ''))
    if parts.scheme not in ('http', 'https'):
        return ''
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def existing_path(record):
    if not isinstance(record, dict) or record.get('status') in ('failed', 'pending'):
        return ''
    value = record.get('path') or record.get('videoPath') or ''
    if not value:
        return ''
    path = ROOT / value
    try:
        path.resolve().relative_to(ROOT.resolve())
        if not path.is_file() or path.stat().st_size == 0:
            return ''
        if record.get('bytes') and path.stat().st_size != int(record['bytes']):
            return ''
    except (ValueError, OSError):
        return ''
    return path.relative_to(ROOT).as_posix()


def md_link(label, path):
    label = label.replace("[", "\\[").replace("]", "\\]")
    return f"[{label}]({quote(path, safe='/:?=&%#')})"


def safe_name(title):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', title).strip('. ')[:150] or '未命名课程'


def parse_description(value):
    if isinstance(value, str):
        try:
            blocks = json.loads(value)
        except json.JSONDecodeError:
            blocks = [{'type': 0, 'value': value}]
    else:
        blocks = value or []
    if not isinstance(blocks, list):
        blocks = []
    return blocks


def format_intro(text):
    # Exact source wording, only restore paragraph/heading breaks around its
    # explicitly numbered outline. No spelling correction or paraphrasing.
    result = text
    for heading in INTRO_HEADINGS:
        result = result.replace(heading, '\n\n## ' + heading + '\n\n', 1)
    return result.strip()


def intro_html(text):
    parts = re.split(r'\n\n', format_intro(text))
    return '\n'.join(f'<h2>{html.escape(p[3:])}</h2>' if p.startswith('## ') else f'<p>{html.escape(p).replace(chr(10), "<br>")}</p>' for p in parts if p)


def build(args):
    raw = read_json(ROOT / '.private/course-raw.json')
    if not raw or not isinstance(raw.get('list'), list):
        raise SystemExit('缺少 .private/course-raw.json，无法生成真实课程目录。')
    assets = read_json(ROOT / 'metadata/assets-manifest.json')
    videos = read_json(ROOT / 'metadata/videos-manifest.json')
    now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    source = unsigned_url(raw.get('source'))
    base = raw.get('base', {}).get('data', {})
    core = raw.get('core', {}).get('data', {})
    title = base.get('title') or core.get('resource_name') or '课程学习室'
    details = {str(x['id']): x for x in raw.get('lessons', [])}
    image_map = assets.get('images', {})
    asset_lessons = assets.get('lessons', {})
    video_lessons = videos.get('lessons', {})
    images = {}
    for remote, record in image_map.items():
        path = existing_path(record)
        if path:
            normalized = unsigned_url(remote)
            images[normalized] = path
            images[normalized.replace('http://', 'https://', 1)] = path
            images[normalized.replace('https://', 'http://', 1)] = path

    def local_image(*urls):
        return next((images.get(unsigned_url(url)) for url in urls if images.get(unsigned_url(url))), '')

    intro_blocks = parse_description(core.get('descrb'))
    intro_text = '\n\n'.join(str(b.get('value', '')) for b in intro_blocks if b.get('type') == 0)
    summary_paragraphs = list(dict.fromkeys(str(value) for value in [base.get('summary'), core.get('summary')] if value))
    course_summary_text = '\n\n'.join(summary_paragraphs)
    intro = format_intro(intro_text)
    (ROOT / 'lessons').mkdir(exist_ok=True)
    (ROOT / 'metadata').mkdir(exist_ok=True)
    (ROOT / 'metadata/course-description.txt').write_text(intro_text, encoding='utf-8')
    (ROOT / 'metadata/course-summary.txt').write_text(course_summary_text, encoding='utf-8')
    summary_section = '<h2>课程简介原文</h2>' + ''.join('<p>' + html.escape(p) + '</p>' for p in summary_paragraphs) if summary_paragraphs else ''
    description = summary_section + '<h2>商品详情原文</h2>' + intro_html(intro_text)
    course_cover = local_image(base.get('img_url'), core.get('resource_img'))
    lessons = []
    for index, item in enumerate(raw['list'], 1):
        lesson_id = str(item['resource_id'])
        record = details.get(lesson_id, {})
        lesson_core = record.get('core', {}).get('data', {})
        detail = record.get('detail', {}).get('data', {})
        info = detail.get('video_info', {})
        lesson_title = item.get('resource_title') or lesson_core.get('resource_name') or lesson_id
        asset = asset_lessons.get(lesson_id, {})
        audio_record = asset.get('audio', {})
        video_record = video_lessons.get(lesson_id, {})
        video_path = existing_path(video_record)
        audio_path = existing_path(audio_record)
        poster = local_image(lesson_core.get('resource_img'), item.get('img_url'), info.get('patch_img_url'))
        audio_expected = bool(info.get('video_audio_url'))
        video_state = 'downloaded' if video_path else video_record.get('videoStatus') or video_record.get('status') or args.video_fallback_state
        if video_state == 'downloaded' and not video_path:
            video_state = 'failed'
        if video_state not in ('downloaded', 'drm', 'pending', 'failed', 'locked', 'unavailable'):
            video_state = args.video_fallback_state
        status = 'downloaded' if video_path and (audio_path or not audio_expected) and poster else 'partial' if audio_path or video_path else 'locked' if video_state in ('drm', 'locked') else 'failed' if video_state in ('failed', 'unavailable') else 'pending'
        lesson_url = urljoin(source, item.get('jump_url', '')) if item.get('jump_url') else source
        duration = video_record.get('media', {}).get('duration') or info.get('video_length') or audio_record.get('media', {}).get('duration') or 0
        media = video_record.get('media', {})
        resolution = f"{media['width']} × {media['height']}" if media.get('width') and media.get('height') else ''
        video_quality = video_record.get('quality') or resolution
        if isinstance(video_quality, dict):
            video_quality = video_quality.get('label') or video_quality.get('name') or resolution
        if resolution and video_quality and resolution not in str(video_quality):
            video_quality = f'{video_quality} · {resolution}'
        # The original pages currently return empty descrb, subtitles disabled,
        # and zero courseware. Store this evidence separately from course content.
        original_blocks = parse_description(lesson_core.get('descrb'))
        text_blocks = [str(b.get('value', '')) for b in original_blocks if b.get('type') == 0 and b.get('value')]
        original_text = '\n\n'.join(text_blocks)
        caption_data = record.get('captions', {}).get('data', [])
        caption_msg = record.get('captions', {}).get('msg', '')
        courseware_total = record.get('courseware', {}).get('data', {}).get('total', 0)
        evidence = '当前课时接口未列出独立图文正文，字幕接口显示未开启，课件附件数量为 0。此 Markdown 为课程资料索引，不是视频逐字稿。'
        if original_text:
            evidence = '以下正文来自原课程页面。'
        elif caption_data or courseware_total:
            evidence = '原课程页面未提供独立图文正文。此 Markdown 为课程资料索引，不是视频逐字稿。'
        markdown_path = f'lessons/{safe_name(lesson_title)}.md'
        local_html = '\n'.join(f'<p>{html.escape(t)}</p>' for t in text_blocks) if original_text else f'<p>{html.escape(evidence)}</p>'
        lesson = {'id': lesson_id, 'title': lesson_title, 'index': index, 'type': 'video', 'status': status, 'videoStatus': video_state,
                  'descriptionHtml': local_html, 'markdownPath': markdown_path, 'videoPath': video_path, 'audioPath': audio_path, 'poster': poster,
                  'attachments': [], 'duration': duration, 'quality': video_quality if video_path else '', 'sourceUrl': lesson_url,
                  'textAvailable': bool(original_text), 'subtitlesAvailable': bool(caption_data), 'coursewareCount': courseware_total}
        lessons.append(lesson)
        lines = [f'# {lesson_title}', '', f'- 原课程：{md_link("打开原页面", lesson_url)}', f'- 保存状态：{STATUS_NAMES[status]}', f'- 原课程时长：{info.get("video_length", 0)} 秒', '']
        if video_path:
            lines += [f'- 本地视频：{md_link("播放视频", "../" + video_path)}', f'- 视频清晰度：{video_quality or "见视频文件元数据"}']
        else:
            video_note = {'drm': '视频受 DRM 保护，需在课程平台观看。', 'pending': '视频下载或访问检查尚未完成。', 'failed': '视频下载未完成。', 'locked': '视频需要相应访问权限。', 'unavailable': '未取得可本地保存的视频。'}.get(video_state, '视频尚未本地保存。')
            lines += [f'- 视频状态：{video_note}']
        lines += [f'- 本地音频：{md_link("收听音频", "../" + audio_path)}' if audio_path else '- 音频状态：尚未本地保存。']
        if poster:
            lines += ['', f'![课程封面]({quote("../" + poster, safe="/")})']
        lines += ['', '## 原页面文字与附件', '', evidence, '']
        if original_text:
            lines += [original_text, '']
        lines += [f'- 页面字幕状态：{caption_msg or ("有字幕数据" if caption_data else "未提供字幕")}', f'- 页面课件附件数量：{courseware_total}', '', '## 我的学习笔记', '', '可在学习网页的「学习笔记」中记录，并导出为独立 Markdown 文件。', '']
        (ROOT / markdown_path).write_text('\n'.join(lines), encoding='utf-8')

    video_count = sum(bool(x['videoPath']) for x in lessons)
    audio_count = sum(bool(x['audioPath']) for x in lessons)
    complete_count = sum(x['status'] == 'downloaded' for x in lessons)
    drm_count = sum(x['videoStatus'] == 'drm' for x in lessons)
    pending_count = sum(x['videoStatus'] == 'pending' for x in lessons)
    image_paths = sorted(set(images.values()))
    summary_parts = [f'目录共 {len(lessons)} 节；已保存本地视频 {video_count} 个、独立音频 {audio_count} 个、图片 {len(image_paths)} 张。']
    if drm_count:
        summary_parts.append(f'{drm_count} 节视频受 DRM 保护，未能本地保存，需在原课程平台观看。')
    if pending_count:
        summary_parts.append(f'{pending_count} 节视频仍在下载或检查中。')
    if video_count < len(lessons) and not (drm_count or pending_count):
        summary_parts.append(f'尚有 {len(lessons) - video_count} 节视频未完整保存。')
    summary_parts.append('已保留课程介绍原文及每节课的 Markdown 索引；当前课时接口未列出独立课文、字幕或课件附件。')
    summary = {'lessonCount': len(lessons), 'videoCount': video_count, 'audioCount': audio_count, 'imageCount': len(image_paths), 'completeCount': complete_count,
               'drmCount': drm_count, 'pendingVideoCount': pending_count, 'message': '\n'.join(summary_parts)}
    course_attachments = [{'name': '课程介绍 · Markdown', 'path': '课程介绍.md', 'kind': 'markdown'}, {'name': '完整课程目录 · Markdown', 'path': '课程目录.md', 'kind': 'markdown'}]
    quality_report = 'metadata/original-quality-investigation.md'
    if (ROOT / quality_report).is_file():
        course_attachments.append({'name': '视频清晰度核验说明', 'path': quality_report, 'kind': 'report'})
    for name, path, kind in [('上传原片深查记录', 'metadata/original-source-deep-investigation.md', 'report'), ('绘本书目 · Markdown', '绘本书目.md', 'markdown')]:
        if (ROOT / path).is_file():
            course_attachments.append({'name': name, 'path': path, 'kind': kind})
    seen_image_paths = set()
    for remote, image_record in image_map.items():
        image_path = existing_path(image_record)
        if not image_path or image_path in seen_image_paths:
            continue
        seen_image_paths.add(image_path)
        variant = '压缩版本' if '/compress/' in remote else '原图'
        course_attachments.append({'name': f'课程图片 {len(seen_image_paths):02d} · {variant}', 'path': image_path, 'kind': 'image', 'bytes': image_record.get('bytes', 0)})
    course = {'title': title, 'sourceUrl': source, 'descriptionHtml': description, 'cover': course_cover, 'lessons': lessons, 'updatedAt': now, 'summary': summary, 'attachments': course_attachments}
    write_json(ROOT / 'course-data.json', course)
    (ROOT / 'course-data.js').write_text('window.COURSE_DATA = ' + json.dumps(course, ensure_ascii=False, indent=2).replace('</', '<\\/') + ';\n', encoding='utf-8')
    intro_doc = f'# {title} · 课程介绍原文\n\n来源：{md_link("原课程页面", source)}\n\n以下保留原页面文字，仅按原编号补充 Markdown 标题与段落。未改写内容或纠正原文用字。\n\n## 课程简介原文\n\n{course_summary_text}\n\n## 商品详情原文\n\n{intro.replace('## ', '### ')}\n'
    (ROOT / '课程介绍.md').write_text(intro_doc, encoding='utf-8')
    table = ['| 序号 | 原课程标题 | 视频 | 音频 | Markdown |', '| --- | --- | --- | --- | --- |']
    for item in lessons:
        video_text = md_link('本地视频', item['videoPath']) if item['videoPath'] else {'drm': 'DRM / 原平台观看', 'pending': '待完成', 'locked': '需访问权限'}.get(item['videoStatus'], '未下载')
        audio_text = md_link('本地音频', item['audioPath']) if item['audioPath'] else '未下载'
        table_title = item["title"].replace("|", "\\|")
        table.append(f'| {item["index"]} | {table_title} | {video_text} | {audio_text} | {md_link("资料索引", item["markdownPath"])} |')
    (ROOT / '课程目录.md').write_text(f'# {title} · 课程目录\n\n' + '\n\n'.join(summary_parts) + '\n\n' + '\n'.join(table) + '\n', encoding='utf-8')
    (ROOT / 'README.md').write_text(f'''# {title} · 本地学习资料

打开 [index.html](index.html) 即可进入学习网页，无需联网、安装依赖或启动服务器。

绘本整理后，可打开 [books.html](books.html) 查看本地封面、提及证据及课程时间入口；[绘本书目.md](绘本书目.md)提供同一书目的 Markdown 版本。

## 实际保存情况

{chr(10).join('- ' + p for p in summary_parts)}

更新时间：{now}

{md_link('原课程页面', source)}

## 如何学习

1. 打开 `index.html`，在课程目录中选课。可搜索名称、按类型或保存状态筛选。
2. 播放本地音频或视频；浏览器会记住播放位置。
3. 点击「标记学完」保存学习进度。在「学习笔记」里记录并导出 Markdown。
4. [课程介绍.md](课程介绍.md) 保存原页面课程介绍；[课程目录.md](课程目录.md) 汇总所有课程入口。
5. `lessons/` 下的 41 份 Markdown 是每课资料索引。当前课时接口未提供正文或字幕；这些索引不是视频逐字稿。

学习进度、笔记和播放位置保存在当前浏览器。清理浏览器数据、更换浏览器或移动文件夹可能影响记录，请先导出笔记。视频播放速度可通过浏览器播放器菜单设置。

## 文件位置

- `media/audio/`：平台提供的独立音频文件。
- `media/videos/`：已成功保存的视频（以各课链接及视频清单为准）。
- `media/images/`：课程封面和原页面图片。
- `media/book-covers/`：课程书目对应的本地封面。
- `books-data.json` / `books-data.js`：绘本书目、封面来源和课程提及位置。
- `metadata/original-source-deep-investigation.md`：上传原片与清晰度深查，含素材逻辑及实际媒体字节对比。
- `lessons/`：逐课 Markdown 索引。
- `metadata/assets-manifest.json`：音频和图片文件大小、SHA-256 与媒体元数据。
- `metadata/videos-manifest.json`：视频清单（取得视频后生成）；以实际路径、清晰度及校验信息为准。
- `metadata/course-summary.txt`：课程简介的原始纯文本。
- `metadata/course-description.txt`：商品详情纲要的原始纯文本。
- `course-data.json` / `course-data.js`：学习网页使用的本地目录数据。
- 学习网页总览的「课程资料」提供课程介绍、完整目录、视频清晰度核验说明（生成后）及全部原页面图片的下载入口。

## 重新生成目录

新增媒体后，先更新对应的 manifest，再执行：

```sh
python3 scripts/build_catalog.py
python3 scripts/build_books.py
```

默认会将尚无本地视频的条目标为「待完成」。只有在确认最终限制后，才使用 `--video-fallback-state drm` 或 `--video-fallback-state failed`。视频清单内每课的状态优先于此参数。脚本仅引用实际存在、大小匹配的本地文件，不从受保护的视频地址推断下载成功。

`.private/` 存放采集过程需要的私有响应，可能含短期访问凭据；学习网页不使用它。分享学习网页文件时不包含该目录。
''', encoding='utf-8')
    write_json(ROOT / 'metadata/catalog-build.json', {'updatedAt': now, 'videoFallbackState': args.video_fallback_state, 'summary': summary})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video-fallback-state', choices=['pending', 'drm', 'failed', 'locked', 'unavailable'], default='pending')
    build(parser.parse_args())
