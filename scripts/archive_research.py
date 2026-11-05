"""Create a credential-free research archive while preserving .private originals.

Offline, deterministic, standard-library only. Does not alter course media or Git.
Run: python scripts/archive_research.py
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.private'
ARCHIVE = ROOT / 'archive'
DEST = ARCHIVE / 'research'
REDACTED = '[REDACTED]'
SENSITIVE_KEYS = {
    'play_sign', 'cookie', 'cookies', 'set-cookie', 'authorization',
    'auth', 'token', 'access_token', 'refresh_token', 'id_token',
    'auth_token', 'api_key', 'apikey', 'x-api-key', 'client_secret',
    'password', 'passwd', 'secret_key', 'private_key', 'csrf_token', 'xsrf_token',
}
SIGNED_QUERY_KEYS = {
    'sign', 'signature', 'token', 'access_token', 'auth_key', 'ak', 'us',
    'key', 'api_key', 'apikey', 'x-amz-signature', 'x-amz-credential',
    'x-amz-security-token', 'csrf_token', 'xsrf_token',
}
SENSITIVE_JSON = {
    'course-raw.json', 'playback-raw.json', 'video-variants.json',
    'quality-research/multi-line-raw.json',
}
PUBLISHER_HTML = {
    'book-research/spot-goes-to-school.html',
    'book-research/spot-goes-to-the-farm.html',
    'book-research/spot-stays-overnight.html',
}
URL_PATTERN = re.compile(r'https?://[^\s<>"\x27`\\]+')
TOKEN_PATTERNS = {
    'private-key-block': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'openai-key': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{25,}'),
    'aws-key-id': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
}
TEXT_EXTENSIONS = {'.json', '.txt', '.md', '.html', '.js', '.py', '.go', '.log', '.m3u8'}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files():
    excluded = set()
    files = []
    for directory, dirs, names in os.walk(PRIVATE):
        here = Path(directory)
        for name in dirs[:]:
            path = here / name
            if name in {'asr-venv', '__pycache__', '.git', 'node_modules'} or path.is_symlink() or operational_file(path):
                excluded.add(path.relative_to(ROOT).as_posix() + '/')
                dirs.remove(name)
        for name in names:
            path = here / name
            if name == '.DS_Store' or path.is_symlink() or operational_file(path):
                excluded.add(path.relative_to(ROOT).as_posix())
            else:
                files.append(path)
    return sorted(files), sorted(excluded)


def operational_file(path: Path) -> bool:
    """Only ignore Git/upload operational state, not downloaded research repos."""
    first = path.relative_to(PRIVATE).parts[0].lower()
    return first.startswith(('git-', 'github-', 'lfs-', 'push-', 'upload-status', 'upload-progress'))


def decode_variants(value):
    if isinstance(value, str) and value.endswith('__ba'):
        raw = value[:-4].translate(str.maketrans('@#$%', '1234'))
        return json.loads(base64.b64decode(raw).decode())
    if isinstance(value, str):
        return json.loads(value)
    return value


def baseline_secrets():
    """The same 303 known account credential values used by the prior audit."""
    found = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'play_sign', 'access_token', 'refresh_token', 'cookie', 'cookies', 'authorization'} and isinstance(item, str) and len(item) > 10:
                    found.add(item)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str) and value.startswith(('http://', 'https://')):
            for key, item in parse_qsl(urlsplit(value).query):
                if key.lower() in {'sign', 'signature', 'ak', 'access_token', 'token', 'auth_key', 'us'} and len(item) > 7:
                    found.add(item)

    for relative in ['course-raw.json', 'playback-raw.json', 'quality-research/multi-line-raw.json']:
        collect(json.loads((PRIVATE / relative).read_text()))
    return found


def all_known_secrets(files, baseline):
    found = set(baseline)

    def collect(value, key=''):
        if isinstance(value, dict):
            for name, item in value.items():
                if name.lower() in SENSITIVE_KEYS and isinstance(item, str) and len(item) > 7:
                    found.add(item)
                if name == 'video_urls':
                    collect(decode_variants(item))
                elif name == 'param' and isinstance(item, str):
                    for name2, item2 in parse_qsl(item):
                        if name2.lower() in SIGNED_QUERY_KEYS and len(item2) > 7:
                            found.add(item2)
                collect(item, name)
        elif isinstance(value, list):
            for item in value:
                collect(item, key)
        elif isinstance(value, str):
            for match in URL_PATTERN.finditer(html.unescape(value)):
                for name, item in parse_qsl(urlsplit(match[0]).query):
                    if name.lower() in SIGNED_QUERY_KEYS and len(item) > 7:
                        found.add(item)

    for path in files:
        relative = path.relative_to(PRIVATE).as_posix()
        if relative in SENSITIVE_JSON:
            collect(json.loads(path.read_text()))
        elif relative in PUBLISHER_HTML or relative == 'first-manifest.m3u8':
            text = html.unescape(path.read_text())
            collect(text)
            for match in re.finditer(r'api_key=([A-Za-z0-9]{16,})', text):
                found.add(match[1])
    return found


def scrub_url(url):
    normalized = html.unescape(url)
    parsed = urlsplit(normalized)
    if any(key.lower() in SIGNED_QUERY_KEYS for key, _ in parse_qsl(parsed.query)):
        # Signed URLs often include expiry/user binding fields in addition to sign.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', parsed.fragment))
    return url


def scrub_text(text, known):
    text = URL_PATTERN.sub(lambda m: scrub_url(m[0]), text)
    # Publisher pages contain both raw URLs and script-escaped API request text.
    text = re.sub(r'(?i)(api_key=)([A-Za-z0-9]{16,})', lambda m: m[1] + REDACTED, text)
    for value in sorted(known, key=len, reverse=True):
        for representation in {value, quote(value, safe=''), html.escape(value, quote=True)}:
            text = text.replace(representation, REDACTED)
    return text


def scrub_json(value, known, changes, key=''):
    if isinstance(value, dict):
        output = {}
        for name, item in value.items():
            if name.lower() in SENSITIVE_KEYS and item not in (None, '', [], {}):
                output[name] = REDACTED
                changes.add('credential fields replaced with [REDACTED]')
            elif name == 'video_urls':
                output[name] = scrub_json(decode_variants(item), known, changes, name)
                changes.add('encoded video_urls decoded to reviewable structured variants; original encoded string omitted')
            elif name == 'param' and isinstance(item, str) and any(k.lower() in SIGNED_QUERY_KEYS for k, _ in parse_qsl(item)):
                output[name] = REDACTED
                changes.add('signed query-string field replaced with [REDACTED]')
            else:
                output[name] = scrub_json(item, known, changes, name)
        return output
    if isinstance(value, list):
        return [scrub_json(item, known, changes, key) for item in value]
    if isinstance(value, str):
        result = scrub_text(value, known)
        if result != value:
            changes.add('signed URL query or known credential value removed')
        return result
    return value


def make_copy(source, known):
    relative = source.relative_to(PRIVATE).as_posix()
    data = source.read_bytes()
    changes = set()
    if relative in SENSITIVE_JSON:
        output = scrub_json(json.loads(data), known, changes)
        result = (json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode()
    elif relative == 'first-manifest.m3u8':
        text = scrub_text(data.decode(), known)
        lines = []
        for line in text.splitlines():
            if line and not line.startswith('#') and '?' in line:
                line = line.split('?', 1)[0]
            lines.append(line)
        result = ('\n'.join(lines) + '\n').encode()
        changes.add('HLS key URI and segment URL signatures removed; no decryption key copied')
    elif relative in PUBLISHER_HTML:
        result = scrub_text(data.decode(), known).encode()
        changes.add('public publisher API-key query values removed from snapshot')
    elif relative == 'initial-login-page.html':
        text = re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>', '', data.decode(), flags=re.I)
        text = re.sub(r'<script\b[^>]*/\s*>', '', text, flags=re.I)
        result = scrub_text(text, known).encode()
        changes.add('login/security-page scripts and dynamic cookie bootstrap removed')
    else:
        result = data
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result)
    return {
        'source': source.relative_to(ROOT).as_posix(),
        'target': target.relative_to(ROOT).as_posix(),
        'sourceBytes': len(data), 'sourceSHA256': digest(data),
        'bytes': len(result), 'sha256': digest(result),
        'redacted': bool(changes),
        'reason': '; '.join(sorted(changes)) if changes else 'Unchanged noncredential research/learning evidence',
    }


def audit(files, known, baseline):
    """No sensitive values or matching lines are returned or printed."""
    findings = []
    checked = 0
    css_false_positives = 0
    baseline_hits = 0
    expanded_hits = 0
    for path in files:
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        text = path.read_text()
        checked += 1
        base_matches = sum(value in text or quote(value, safe='') in text for value in baseline)
        all_matches = sum(value in text or quote(value, safe='') in text for value in known)
        baseline_hits += base_matches
        expanded_hits += all_matches
        if all_matches:
            findings.append((path.relative_to(ROOT).as_posix(), 'known-credential'))
        for name, pattern in TOKEN_PATTERNS.items():
            for match in pattern.finditer(text):
                token = match[0]
                context = text[max(0, match.start()-150):match.end()+150]
                # The fetched public JS has sk-... CSS animation identifiers.
                if name == 'openai-key' and token == token.lower() and re.search(r'keyframes|animation:|webkit|transform:|background:', context):
                    css_false_positives += 1
                    continue
                findings.append((path.relative_to(ROOT).as_posix(), name))
        for match in URL_PATTERN.finditer(text):
            for name, value in parse_qsl(urlsplit(html.unescape(match[0])).query):
                if name.lower() in SIGNED_QUERY_KEYS and value not in {REDACTED, '', 'xe_xxxxx'}:
                    findings.append((path.relative_to(ROOT).as_posix(), 'signed-URL-query'))
    return {
        'textFilesScanned': checked,
        'baselineKnownSecretCount': len(baseline),
        'expandedKnownSecretCount': len(known),
        'baselineSecretOccurrences': baseline_hits,
        'expandedSecretOccurrences': expanded_hits,
        'credentialPatternFindings': len(findings),
        'reviewedPublicCSSIdentifierFalsePositives': css_false_positives,
    }, findings


def main():
    files, excluded = source_files()
    baseline = baseline_secrets()
    known = all_known_secrets(files, baseline)
    records = [make_copy(path, known) for path in files]
    README = '''# 课程研究归档

本目录保留课程整理过程产生的机器转写、抽帧与联系图、书目研究快照、公开播放器源码、研究脚本、日志和接口证据。文件在 `research/` 下保持 `.private/` 内的原相对路径，逐文件清单见 `research-manifest.json`。

完整课程视频、音频、图片、文字和学习网页保持原样；本次归档没有改动课程内容。`.private/` 原始文件也保持不变。登录或播放凭据只保留在本地原件中，入库副本已删除签名 URL 查询并将实际凭据字段替换为 `[REDACTED]`；编码的 `video_urls` 已解码为可审查的结构，再做脱敏。登录安全验证页移除了脚本，出版社公开网页中内嵌的 API key 也已清除。普通源码中的参数名称与接口定义保留。

机器转写和书目识别过程可能包含误识别或待核候选，应结合课程视频与最终书目证据阅读。

`asr-venv/` 等 Python 依赖环境、字节码缓存和 Git/上传操作临时状态不属于课程或研究结果，不入库，原件仍保留在本地。约 1.13 GB 的转写运行环境可按项目脚本所用依赖重新安装。公开第三方源码按原研究快照保存，不作为可执行下载器调用。

重建归档：在保留 `.private/` 原始研究数据的本机执行 `python scripts/archive_research.py`。脚本只读原件、生成本目录，并检查已知凭据及常见凭据模式；不会联网或执行 Git 操作。
'''
    (ARCHIVE / 'README.md').write_text(README)
    manifest = {
        'schemaVersion': 1,
        'sourceRoot': '.private', 'archiveRoot': 'archive/research',
        'originalsModified': False, 'courseMediaModified': False,
        'files': records,
        'excludedPaths': excluded,
        'excludedReason': 'Rebuildable runtime/cache or Git/upload operational state; local originals retained',
    }
    manifest_path = ARCHIVE / 'research-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    audit_result, findings = audit([p for p in ARCHIVE.rglob('*') if p.is_file()], known, baseline)
    if findings:
        print(json.dumps({'audit': audit_result, 'ready': False}, ensure_ascii=False))
        raise RuntimeError('Archive audit found credential candidates; do not commit archive yet')
    manifest['audit'] = audit_result
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({
        'archivedFiles': len(records),
        'redactedFiles': sum(item['redacted'] for item in records),
        'unchangedFiles': sum(not item['redacted'] for item in records),
        'archivedBytes': sum(item['bytes'] for item in records),
        'excludedPathCount': len(excluded),
        'audit': audit_result, 'ready': True,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
