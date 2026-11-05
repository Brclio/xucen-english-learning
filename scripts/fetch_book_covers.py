#!/usr/bin/env python3
"""Archive official covers for the 25 books explicitly named in lessons 16–40."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import unescape
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from assets import download

ROOT = Path(__file__).resolve().parent.parent
SERIES_URL = 'https://books.disney.com/character-series/elephant-and-piggie/'
SLUGS = [
    'my-friend-is-sad', 'today-i-will-fly', 'there-is-a-bird-on-your-head',
    'i-am-invited-to-a-party', 'i-love-my-new-toy', 'i-will-surprise-my-friend',
    'are-you-ready-to-play-outside', 'watch-me-throw-the-ball', 'elephants-cannot-dance',
    'pigs-make-me-sneeze', 'i-am-going', 'can-i-play-too', 'we-are-in-a-book',
    'i-broke-my-trunk', 'should-i-share-my-ice-cream', 'happy-pig-day',
    'listen-to-my-trumpet', 'lets-go-for-a-drive', 'a-big-guy-took-my-ball',
    'im-a-frog', 'my-new-friend-is-so-fun', 'waiting-is-not-easy',
    'i-will-take-a-nap', 'i-really-like-slop', 'the-thank-you-book',
]


def page(url, name):
    path = ROOT / '.private/book-research' / (name + '.html')
    if path.exists():
        return path.read_text()
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60) as response:
        body = response.read().decode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return body


def isbn13_valid(value):
    return len(value) == 13 and value.isdigit() and sum(int(x) * (1 if i % 2 == 0 else 3) for i, x in enumerate(value)) % 10 == 0


def archive(slug, lesson):
    url = f'https://books.disney.com/book/{slug}/'
    body = page(url, slug)
    marker = 'var BLUECORE_PRODUCT_DATA = '
    if marker not in body:
        raise ValueError(f'Publisher metadata missing for {slug}')
    data, _ = json.JSONDecoder().raw_decode(body.split(marker, 1)[1])
    if not isbn13_valid(data['id']) or data['author'] != 'Mo Willems':
        raise ValueError(f'Unexpected identity for {slug}')
    cover_url = data['image'].replace('http://', 'https://', 1)
    suffix = Path(cover_url.split('?', 1)[0]).suffix.lower()
    path = f'media/book-covers/{slug}{suffix}'
    asset = download(cover_url, path, referer=url)
    size = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', path], capture_output=True, text=True, check=True)
    width = re.search(r'pixelWidth: (\d+)', size.stdout)
    height = re.search(r'pixelHeight: (\d+)', size.stdout)
    if not width or not height:
        raise ValueError(f'Cover cannot be decoded for {slug}')
    return {
        'id': 'elephant-piggie-' + slug,
        'title': unescape(data['name']),
        'author': 'Mo Willems',
        'illustrator': data.get('illustrated_by', 'Mo Willems'),
        'series': 'Elephant & Piggie',
        'cover': path,
        'sourceUrl': url,
        'coverSourceUrl': cover_url,
        'isbn': data['id'],
        'publisher': data.get('imprint', 'Hyperion Books for Children'),
        'pages': int(data.get('pages', 64)),
        'released': data.get('released'),
        'lessonIds': [lesson['id']],
        'mentionEvidence': [{'lessonId': lesson['id'], 'kind': 'lesson-title', 'lessonTitle': lesson['title']}],
        'coverMetadata': {'width': int(width.group(1)), 'height': int(height.group(1)), 'bytes': asset['bytes'], 'sha256': asset['sha256'], 'selection': 'Publisher product metadata points to the original cover image, not a resized thumbnail.'},
    }


def main():
    os.chdir(ROOT)
    course = json.loads((ROOT / 'course-data.json').read_text())
    lessons = course['lessons'][16:41]
    assert len(lessons) == len(SLUGS) == 25
    listing = page(SERIES_URL, 'series')
    links = set(re.findall(r'href=[\"\'](https://books.disney.com/book/[^\"\']+)', listing))
    for slug in SLUGS:
        assert f'https://books.disney.com/book/{slug}/' in links, f'Book absent from observed publisher series list: {slug}'
    books = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(archive, slug, lesson): index for index, (slug, lesson) in enumerate(zip(SLUGS, lessons))}
        for future in as_completed(jobs):
            book = future.result()
            books[jobs[future]] = book
            print(f'{len(books):02}/25 {book["title"]}: cover saved', flush=True)
    result = {
        'checkedAt': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'scope': '课程第16至40节标题直接点名的25本书；不将同系列其他作品或推荐作品当作课程提及。',
        'seriesInfo': {'name': 'Elephant & Piggie', 'author': 'Mo Willems', 'description': '莫·威廉斯创作并绘制的初级阅读系列，主角是大象 Gerald 和小猪 Piggie。此清单的25本书逐一对应课程标题中的绘本讲读课。', 'sourceUrl': SERIES_URL, 'additionalSourceUrl': 'https://www.penguinrandomhouse.com/series/PGB/an-elephant-and-piggie-book/'},
        'books': [books[i] for i in range(25)],
    }
    path = ROOT / 'metadata/book-catalog-source.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Complete: {len(result["books"])} verified official covers; manifest {path.name}', flush=True)


if __name__ == '__main__':
    main()
