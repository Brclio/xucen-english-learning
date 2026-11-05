#!/usr/bin/env python3
"""Download all exposed course audio and image assets; reruns reuse verified files.

Run from anywhere: python3 scripts/download_assets.py
Private signed sources remain in .private/course-raw.json. The public manifest
contains only query-free provenance URLs and local verification details.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from assets import AssetError, download

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'metadata/assets-manifest.json'


def public_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, '', ''))


def safe_name(value):
    return re.sub(r'[\x00-\x1f/\\:*?"<>|]', '_', value).strip('. ')[:180]


def image_urls(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from image_urls(item)
    elif isinstance(value, list):
        for item in value:
            yield from image_urls(item)
    elif isinstance(value, str):
        for candidate in re.findall(r'https?://[^\s<>"\']+', html.unescape(value).replace('\\/', '/')):
            candidate = candidate.rstrip('),;]')
            if re.search(r'\.(?:jpe?g|png|gif|webp|bmp|svg)$', urlsplit(candidate).path, re.I):
                yield candidate


def write_manifest(data):
    data['updatedAt'] = datetime.now().astimezone().isoformat()
    audios = [item['audio'] for item in data['lessons'].values()]
    images = {item['path']: item for item in data['images'].values() if item.get('status') == 'downloaded'}
    data['summary'] = {
        'audioCount': sum(item.get('status') == 'downloaded' for item in audios),
        'imageCount': len(images),
        'audioBytes': sum(item.get('bytes', 0) for item in audios if item.get('status') == 'downloaded'),
        'imageBytes': sum(item.get('bytes', 0) for item in images.values()),
        'errors': [item.get('error', 'unknown error') for item in audios + list(data['images'].values()) if item.get('status') == 'failed'],
    }
    MANIFEST.parent.mkdir(exist_ok=True)
    temp = MANIFEST.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(MANIFEST)


def main():
    os.chdir(ROOT)
    raw = json.loads((ROOT / '.private/course-raw.json').read_text())
    titles = {item['resource_id']: item['resource_title'] for item in raw['list']}
    manifest = {'sourceUrl': public_url(raw['source']), 'lessons': {}, 'images': {}}
    jobs = []
    referer = raw['source']
    for lesson in raw['lessons']:
        lesson_id = lesson['id']
        title = titles[lesson_id]
        info = lesson.get('detail', {}).get('data', {}).get('video_info', {})
        audio_url = info.get('video_audio_url')
        record = {'id': lesson_id, 'title': title, 'audio': {'status': 'pending', 'expectedDuration': info.get('video_length')}}
        manifest['lessons'][lesson_id] = record
        if audio_url:
            jobs.append(('audio', lesson_id, audio_url, f'media/audio/{safe_name(title)}.mp3'))
        else:
            record['audio'].update(status='failed', error=f'{title}: no exposed audio URL')

    image_sources = [raw.get('base', {}).get('data', {}), raw.get('core', {}).get('data', {}), raw['list']]
    for lesson in raw['lessons']:
        image_sources += [lesson.get('core', {}).get('data', {}), lesson.get('detail', {}).get('data', {}).get('video_info', {})]
    normalized = {}
    for url in image_urls(image_sources):
        p = urlsplit(url)
        fetch_url = urlunsplit(('https', p.netloc, p.path, p.query, ''))
        normalized.setdefault(fetch_url, set()).add(public_url(url))
    for fetch_url, aliases in sorted(normalized.items()):
        p = urlsplit(fetch_url)
        suffix = Path(p.path).suffix.lower()
        name = hashlib.sha256(public_url(fetch_url).encode()).hexdigest()[:16]
        path = f'media/images/{name}{suffix}'
        jobs.append(('image', fetch_url, fetch_url, path))
        for alias in aliases:
            manifest['images'][alias] = {'status': 'pending', 'sourceUrl': alias}
    write_manifest(manifest)
    print(f'Downloading {len(raw["lessons"])} audio tracks and {len(normalized)} distinct image URLs.', flush=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(download, url, path, referer=referer): (kind, key, url, path) for kind, key, url, path in jobs}
        for future in as_completed(pending):
            kind, key, url, path = pending[future]
            try:
                result = future.result()
                result.update(status='downloaded', sourceUrl=public_url(url))
                if kind == 'audio':
                    expected = manifest['lessons'][key]['audio']['expectedDuration']
                    actual = result['media']['duration']
                    result.update(expectedDuration=expected, durationDelta=round(actual - expected, 3) if expected else None)
                    if expected and abs(actual - expected) > 2:
                        raise AssetError('Audio duration differs from course metadata by more than two seconds.')
            except Exception as error:
                message = str(error) if isinstance(error, AssetError) else type(error).__name__
                result = {'path': path, 'status': 'failed', 'sourceUrl': public_url(url), 'error': message}
            if kind == 'audio':
                record = manifest['lessons'][key]
                record['audio'] = result
                print(f'Audio {record["title"]}: {result["status"]}', flush=True)
            else:
                for alias in normalized[key]:
                    manifest['images'][alias] = {**result, 'sourceUrl': alias}
                print(f'Image {Path(path).name}: {result["status"]}', flush=True)
            write_manifest(manifest)
    print(json.dumps(manifest['summary'], ensure_ascii=False), flush=True)
    return 1 if manifest['summary']['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
