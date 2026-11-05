"""Verify the local archive against its captured 41-lesson inventory."""
from __future__ import annotations
import concurrent.futures as cf
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def check_audio(pair):
    rid, lesson = pair
    item = lesson['audio']
    path = ROOT / item['path']
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, text=True, timeout=180)
    return rid, {'path': item['path'], 'valid': result.returncode == 0 and not result.stderr.strip(), 'fullDecode': result.returncode == 0 and not result.stderr.strip(), 'error': result.stderr[:1200]}

def main():
    assets = json.loads((ROOT / 'metadata/assets-manifest.json').read_text())
    raw = json.loads((ROOT / '.private/course-raw.json').read_text())
    course = json.loads((ROOT / 'course-data.json').read_text())
    videos = json.loads((ROOT / 'metadata/videos-manifest.json').read_text())
    validation = json.loads((ROOT / 'metadata/video-validation.json').read_text())
    errors = []
    expected = {x['resource_id'] for x in raw['list']}
    if len(expected) != 41 or {x['id'] for x in course['lessons']} != expected:
        errors.append('课程目录不完整')
    records = list({x['path']: x for x in [r['audio'] for r in assets['lessons'].values()] + list(assets['images'].values()) + list(videos['lessons'].values())}.values())
    for record in records:
        path = ROOT / record['path']
        if not path.is_file() or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            errors.append('文件校验失败: ' + record['path'])
    for lesson in course['lessons']:
        for key in ('videoPath', 'audioPath', 'poster', 'markdownPath'):
            if not lesson.get(key) or not (ROOT / lesson[key]).is_file():
                errors.append(lesson['title'] + ' 缺少 ' + key)
        if lesson['status'] != 'downloaded':
            errors.append(lesson['title'] + ' 未完成')
        if not validation['lessons'].get(lesson['id'], {}).get('valid'):
            errors.append(lesson['title'] + ' 视频未通过全片解码')
    for path in list(ROOT.glob('*.md')) + list((ROOT / 'lessons').glob('*.md')):
        for target in re.findall(r'\]\(([^\n]+?)\)', path.read_text()):
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            local = path.parent / unquote(target.split('#')[0])
            if not local.exists():
                errors.append(f'{path.name} 本地链接缺失: {target}')
    audio_results = {}
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        for rid, result in pool.map(check_audio, assets['lessons'].items()):
            audio_results[rid] = result
            if not result['valid']:
                errors.append('音频解码失败: ' + result['path'])
    report = {'expectedLessons': 41, 'catalogLessons': len(course['lessons']), 'videoCount': len(videos['lessons']), 'audioCount': len(assets['lessons']), 'imageCount': len({x['path'] for x in assets['images'].values()}), 'mediaBytes': sum(x['bytes'] for x in records), 'fullVideoDecodeCount': sum(x.get('valid', False) for x in validation['lessons'].values()), 'fullAudioDecodeCount': sum(x['valid'] for x in audio_results.values()), 'audioValidation': audio_results, 'errors': errors, 'complete': not errors}
    (ROOT / 'metadata/archive-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    duration = sum(x['media']['duration'] for x in videos['lessons'].values())
    text = f'''# 课程本地化验收报告

- 课程：许岑的英语启蒙方法论
- 完整目录：{report['catalogLessons']} / 41 节
- 本地视频：{report['videoCount']} 个 MP4，均为 1280×720，保留原编码，无画面重压缩
- 独立音频：{report['audioCount']} 个 MP3，保留平台提供的文件
- 课程图片：{report['imageCount']} 个文件，包含原图与页面提供的封面版本
- 课程音视频及原页面图片总量：{report['mediaBytes']:,} 字节（{report['mediaBytes'] / 1_000_000_000:.2f} GB）
- 视频合计时长：{int(duration)//3600} 小时 {int(duration)%3600//60} 分 {int(duration)%60} 秒
- 文字：课程简介和商品详情原文、完整目录、41 份逐课 Markdown 资料索引
- 全片解码：{report['fullVideoDecodeCount']} 个视频、{report['fullAudioDecodeCount']} 个音频通过
- 文件大小、SHA-256、本地链接核验：{'通过' if not errors else '有未通过项目，见 JSON 报告'}

## 清晰度与上传原片

41 节课的当前账号播放列表均只提供 720p 视频；已保存这个最高可用档位。首、中、末三课的 B/C 备用线路抽查结果相同。未发现可访问的上传原视频地址，也没有得到上传原视频的分辨率，不能据此判断上传原片本身只有 720p。详见[原画核查记录](metadata/original-quality-investigation.md)。

追加调查闭合读取播放器实际依赖的 166 个源码模块，核对 41 个课程与素材标识，并追踪上传 SDK 的源对象生成及回查逻辑。旧多云接口返回的 4 课、2 条线路、首中末共 24 个分片已实际解密探测，各课两路对应媒体字节相同，均为 1280×720。仍未找到上传原片地址；原片是否留存、原始分辨率多少仍未知。详见[上传原片深查](metadata/original-source-deep-investigation.md)。

## 文字、字幕和附件

专栏及全部 41 节课的课件接口均成功返回零附件；41 节课均未提供独立正文，字幕接口返回未开启。逐课 Markdown 是资料索引，不是视频逐字稿。课程简介及商品详情中的原始文字已完整保留。详见[资源审计](metadata/resource-audit.json)。

## 离线使用

打开 [index.html](index.html) 即可学习。支持搜索、播放位置记忆、学习进度和笔记导出。浏览器核验覆盖全部 82 个音视频引用、首中末课程播放与跳转、手机布局，以及无远程资源请求，详见[网页验收记录](metadata/browser-verification.json)。

05、12 两课的源媒体存在重复时间戳；本地版本仅修正时间戳，逐包对比确认视频及音频编码内容没有增删或重编码。修正证据保存在 metadata 目录。

完整文件指纹见 [SHA256SUMS.txt](SHA256SUMS.txt)，机器可读验收结果见[归档核验](metadata/archive-validation.json)。
'''
    (ROOT / '验收报告.md').write_text(text)
    deliverables = [p for folder in ('media', 'lessons') for p in (ROOT / folder).rglob('*') if p.is_file() and not any(part.startswith('.') for part in p.relative_to(ROOT).parts)]
    deliverables += [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.html', '.css', '.js', '.json', '.md')]
    (ROOT / 'SHA256SUMS.txt').write_text('\n'.join(f'{digest(p)}  {p.relative_to(ROOT)}' for p in sorted(deliverables)) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'audioValidation'}, ensure_ascii=False))
    raise SystemExit(0 if not errors else 1)

if __name__ == '__main__':
    main()
