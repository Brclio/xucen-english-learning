"""Small, dependency-free asset download helpers for an offline course archive.

Public functions return JSON-serializable dictionaries and never print URLs,
headers or subprocess stderr. Callers should retain result dictionaries in their
manifest. Destinations are paths relative to the current working directory (or
absolute paths). curl and ffmpeg/ffprobe must be installed.

    result = download(url, 'media/videos/001.mp4', referer=course_url)
    selection = choose_highest([{'url': url, 'height': 1080, 'bitrate': 4200000}])
    result = download_hls(selection['variant']['url'], 'media/videos/001.mp4')

HLS support is deliberately limited to unencrypted, complete VOD playlists.
Master playlists are inspected and the highest resolution variant is selected.
An external default audio rendition is preserved when present. No transcoding.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


class AssetError(RuntimeError):
    """A download or media verification failed; message contains no secrets."""


_locks: dict[str, threading.RLock] = {}
_lock_guard = threading.Lock()
_MEDIA_EXT = {'.mp4', '.m4v', '.mov', '.webm', '.mp3', '.m4a', '.aac', '.ogg', '.wav', '.flac', '.ts'}


def _lock(path: Path):
    with _lock_guard:
        return _locks.setdefault(str(path.resolve()), threading.RLock())


def _safe_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in {'http', 'https'} or not p.hostname:
        raise AssetError('Only HTTP(S) asset URLs are supported.')
    if any(c in url for c in '\r\n\0'):
        raise AssetError('Invalid URL.')
    return url


def _headers(referer=None, headers=None):
    values = {'User-Agent': 'Mozilla/5.0', **(headers or {})}
    if referer:
        values['Referer'] = referer
    for k, v in values.items():
        if not isinstance(k, str) or not isinstance(v, str) or any(c in k + v for c in '\r\n\0'):
            raise AssetError('Invalid HTTP header.')
    return values


def sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path) -> dict:
    """Read and verify nonempty audio/video streams with ffprobe.

    This verifies container and stream metadata, not a full decode of every frame.
    """
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise AssetError('Media file is missing or empty.')
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode:
            raise AssetError('ffprobe could not read the media container.')
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise AssetError('ffprobe is unavailable or media inspection timed out.') from error
    streams = [s for s in data.get('streams', []) if s.get('codec_type') in {'video', 'audio'}]
    if not streams:
        raise AssetError('Media container has no audio or video stream.')
    duration = _number(data.get('format', {}).get('duration'))
    if duration <= 0:
        duration = max((_number(s.get('duration')) for s in streams), default=0)
    if duration <= 0:
        raise AssetError('Media duration is not positive; file may be incomplete.')
    return {
        'duration': duration,
        'format': data.get('format', {}).get('format_name', ''),
        'bitrate': int(_number(data.get('format', {}).get('bit_rate'))),
        'streams': [{k: s[k] for k in ('codec_type', 'codec_name', 'width', 'height', 'bit_rate', 'sample_rate', 'channels') if k in s} for s in streams],
        'width': max((int(s.get('width', 0)) for s in streams), default=0),
        'height': max((int(s.get('height', 0)) for s in streams), default=0),
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rank(variant):
    width, height = int(_number(variant.get('width'))), int(_number(variant.get('height')))
    resolution = str(variant.get('resolution', variant.get('quality', '')))
    match = re.search(r'(\d{2,5})\s*[xX×]\s*(\d{2,5})', resolution)
    if match and not (width and height):
        width, height = map(int, match.groups())
    if not height:
        match = re.search(r'(\d{3,4})[pP]', resolution)
        if match:
            height = int(match.group(1))
    # Infer area only for ranking when a provider supplies height alone.
    area = width * height if width and height else height * height * 16 / 9
    bitrate = int(_number(variant.get('bitrate', variant.get('bandwidth', variant.get('bit_rate', 0)))))
    return (area, height, bitrate)


def choose_highest(variants) -> dict:
    """Rank exposed variants by pixel count, height, then bitrate.

    Input dictionaries are preserved. Bitrate values must use a common unit.
    A provider's 'original' label alone does not prove a higher resolution.
    """
    variants = list(variants)
    if not variants:
        raise AssetError('No media variants were supplied.')
    ranked = sorted(variants, key=_rank, reverse=True)
    selected = ranked[0]
    rank = _rank(selected)
    return {
        'variant': dict(selected),
        'reason': 'Highest exposed pixel count, then height, then bitrate.' if rank[0] else 'Resolution unavailable; selected highest exposed bitrate. Highest resolution remains unverified.',
        'resolutionKnown': bool(rank[0]),
        'candidateCount': len(variants),
    }


def _verify(path, expected_ext=None):
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise AssetError('Downloaded asset is empty.')
    ext = expected_ext or path.suffix.lower()
    with path.open('rb') as handle:
        prefix = handle.read(512).lstrip().lower()
    if ext not in {'.html', '.htm', '.txt', '.md', '.json', '.xml'} and (prefix.startswith(b'<!doctype html') or prefix.startswith(b'<html')):
        raise AssetError('Asset endpoint returned an HTML page instead of a file.')
    return probe(path) if ext in _MEDIA_EXT else None


def _result(path, reused=False, media=None, **extra):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path), 'reused': reused, 'media': media, **extra}


def _curl_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'


def download(url, relative_dest, referer=None, headers=None) -> dict:
    """Download with curl, resuming .part files and atomically publishing success.

    Existing nonempty, valid files are reused. Returned hashes allow the caller
    to detect later changes. The URL and authorization headers live only in a
    private temporary curl config and are never printed or put in argv.
    """
    _safe_url(url)
    dest = Path(relative_dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    with _lock(dest):
        if dest.exists():
            media = _verify(dest)
            return _result(dest, reused=True, media=media)
        config = '\n'.join([
            'url = ' + _curl_quote(url), 'output = ' + _curl_quote(part.resolve()),
            'location', 'fail', 'silent', 'show-error', 'connect-timeout = 30',
            'speed-limit = 1024', 'speed-time = 90', 'retry = 4', 'retry-delay = 2',
            'retry-connrefused', 'proto = "=http,https"', 'proto-redir = "=http,https"',
            *['header = ' + _curl_quote(f'{k}: {v}') for k, v in _headers(referer, headers).items()],
        ])
        with tempfile.NamedTemporaryFile('w', prefix='course-curl-', suffix='.conf', encoding='utf-8') as cfg:
            cfg.write(config + '\n')
            cfg.flush()
            try:
                result = subprocess.run(['curl', '--config', cfg.name, '--continue-at', '-'], capture_output=True)
                if result.returncode == 33:
                    # This server ignores range requests: restart the unpublished file.
                    part.unlink(missing_ok=True)
                    result = subprocess.run(['curl', '--config', cfg.name], capture_output=True)
            except OSError as error:
                raise AssetError('curl could not be launched.') from error
        if result.returncode:
            raise AssetError(f'curl download failed (exit {result.returncode}); partial file retained for retry.')
        media = _verify(part, dest.suffix.lower())
        os.replace(part, dest)
        return _result(dest, media=media)


def _attrs(line):
    return {m.group(1): m.group(2).strip('"') for m in re.finditer(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line.partition(':')[2])}


def _playlist(url, headers):
    _safe_url(url)
    try:
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            _safe_url(response.url)
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise AssetError('HLS playlist exceeds the inspection limit.')
        text = raw.decode('utf-8-sig')
    except (OSError, UnicodeError) as error:
        raise AssetError('HLS playlist could not be retrieved.') from error
    if not text.lstrip().startswith('#EXTM3U'):
        raise AssetError('HLS endpoint did not return a playlist.')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if line.startswith(('#EXT-X-KEY:', '#EXT-X-SESSION-KEY:')) and _attrs(line).get('METHOD') != 'NONE':
            raise AssetError('Encrypted HLS is not supported by this plain-media downloader.')
    return lines, response.url


def download_hls(url, relative_dest, referer=None, headers=None) -> dict:
    """Select highest unencrypted HLS VOD and remux it to MP4 without re-encoding."""
    dest = Path(relative_dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    with _lock(dest):
        if dest.exists():
            return _result(dest, reused=True, media=probe(dest))
        request_headers = _headers(referer, headers)
        audio_url, selection, expected_duration = None, None, None
        for depth in range(5):
            lines, effective_url = _playlist(url, request_headers)
            variants = []
            audio_groups = [_attrs(line) for line in lines if line.startswith('#EXT-X-MEDIA:') and _attrs(line).get('TYPE') == 'AUDIO']
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF:'):
                    attrs = _attrs(line)
                    if i + 1 >= len(lines) or lines[i + 1].startswith('#'):
                        raise AssetError('Malformed HLS master playlist.')
                    variants.append({'url': urljoin(effective_url, lines[i + 1]), 'resolution': attrs.get('RESOLUTION', ''), 'bitrate': attrs.get('AVERAGE-BANDWIDTH', attrs.get('BANDWIDTH', 0)), 'audioGroup': attrs.get('AUDIO')})
            if variants:
                selection = choose_highest(variants)
                selected = selection['variant']
                url = selected['url']
                group = [g for g in audio_groups if g.get('GROUP-ID') == selected.get('audioGroup') and g.get('URI')]
                if group:
                    audio = next((g for g in group if g.get('DEFAULT') == 'YES'), group[0])
                    audio_url = urljoin(effective_url, audio['URI'])
                continue
            if '#EXT-X-ENDLIST' not in lines:
                raise AssetError('HLS playlist is live or incomplete; no full offline download can be verified.')
            expected_duration = sum(_number(line.partition(':')[2].split(',')[0]) for line in lines if line.startswith('#EXTINF:'))
            url = effective_url
            break
        else:
            raise AssetError('HLS master nesting is too deep.')
        if audio_url:
            audio_lines, audio_url = _playlist(audio_url, request_headers)
            if '#EXT-X-ENDLIST' not in audio_lines or any(x.startswith('#EXT-X-STREAM-INF:') for x in audio_lines):
                raise AssetError('External HLS audio is not a complete media playlist.')
        # ffmpeg receives headers directly but nothing is logged; returned errors
        # intentionally omit stderr, which can contain signed URLs or cookies.
        header_string = ''.join(f'{k}: {v}\r\n' for k, v in request_headers.items())
        args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-protocol_whitelist', 'http,https,tcp,tls', '-headers', header_string, '-i', url]
        if audio_url:
            args += ['-protocol_whitelist', 'http,https,tcp,tls', '-headers', header_string, '-i', audio_url, '-map', '0:v:0?', '-map', '1:a:0']
        else:
            args += ['-map', '0:v:0?', '-map', '0:a:0?']
        args += ['-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', str(part)]
        try:
            result = subprocess.run(args, capture_output=True)
        except OSError as error:
            raise AssetError('ffmpeg could not be launched.') from error
        if result.returncode:
            raise AssetError(f'ffmpeg remux failed (exit {result.returncode}); no completed file published.')
        media = probe(part)
        if expected_duration and abs(media['duration'] - expected_duration) > max(3, expected_duration * .01):
            raise AssetError('HLS output duration differs from the full playlist; no completed file published.')
        if selection:
            rank = _rank(selection['variant'])
            if rank[1] and media['height'] != rank[1]:
                raise AssetError('HLS output resolution differs from the selected highest variant.')
        os.replace(part, dest)
        # Avoid retaining temporary signed URLs in returned quality metadata.
        quality = None if not selection else {**selection, 'variant': {k: v for k, v in selection['variant'].items() if k != 'url'}}
        return _result(dest, media=media, qualitySelection=quality, expectedDuration=expected_duration)
