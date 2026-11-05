"""Upload and verify every complete course MP4 in the course-v1 GitHub Release."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'Brclio/xucen-english-learning'
TAG = 'course-v1'
manifest = json.loads((ROOT / 'metadata/release-file-map.json').read_text())
videos = sorted(manifest['files'], key=lambda item: item['assetName'])

def gh(*args):
    return subprocess.run(['gh', *args], cwd=ROOT, capture_output=True, text=True)

lookup = gh('release', 'view', TAG, '--repo', REPOSITORY, '--json', 'databaseId')
if lookup.returncode:
    raise RuntimeError('Create the course-v1 Release before uploading: ' + lookup.stderr.strip())
release_id = json.loads(lookup.stdout)['databaseId']

def release():
    result = gh('api', f'repos/{REPOSITORY}/releases/{release_id}')
    if result.returncode:
        raise RuntimeError('Create the course-v1 Release before uploading: ' + result.stderr.strip())
    return json.loads(result.stdout)

def asset_matches(asset, record):
    return asset.get('state') == 'uploaded' and asset.get('size') == record['bytes'] and asset.get('digest') == 'sha256:' + record['sha256']

def upload(record):
    path = ROOT / record['originalPath']
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if path.stat().st_size != record['bytes'] or actual != record['sha256']:
        raise RuntimeError('Local video differs from preserved manifest: ' + path.name)
    alias = ROOT / '.private/release-assets' / record['assetName']
    alias.parent.mkdir(parents=True, exist_ok=True)
    if not alias.exists():
        os.link(path, alias)
    elif alias.stat().st_ino != path.stat().st_ino:
        raise RuntimeError('Unexpected local Release staging file: ' + alias.name)
    for attempt in range(3):
        assets = {asset['name']: asset for asset in release()['assets']}
        existing = assets.get(record['assetName'])
        if existing:
            if not asset_matches(existing, record):
                raise RuntimeError('Release asset already exists with different bytes: ' + path.name)
            print('VERIFIED ' + path.name, flush=True)
            return
        result = gh('release', 'upload', TAG, str(alias) + '#' + record['title'], '--repo', REPOSITORY)
        if result.returncode == 0:
            print('UPLOADED ' + path.name, flush=True)
            return
        if attempt < 2:
            print(f'RETRY {path.name} ({attempt + 1})', flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError('Upload failed: ' + path.name + ': ' + result.stderr.strip())

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(upload, sorted(videos, key=lambda item: item['bytes'])))

for document in ('release-video-SHA256SUMS.txt', 'release-file-map.json'):
    checksum = ROOT / 'metadata' / document
    assets = {asset['name']: asset for asset in release()['assets']}
    if checksum.name not in assets:
        result = gh('release', 'upload', TAG, str(checksum), '--repo', REPOSITORY)
        if result.returncode:
            raise RuntimeError('Metadata-file upload failed: ' + result.stderr.strip())
remote = release()
assets = {asset['name']: asset for asset in remote['assets']}
results = []
for record in videos:
    name = record['assetName']
    asset = assets.get(name, {})
    if not asset_matches(asset, record):
        raise RuntimeError('Remote checksum verification failed: ' + name)
    results.append({'name': name, 'originalPath': record['originalPath'], 'title': record['title'], 'bytes': record['bytes'], 'sha256': record['sha256'], 'url': asset['browser_download_url'], 'remoteDigestVerified': True})
report = {'repository': REPOSITORY, 'tag': TAG, 'releaseUrl': remote['html_url'], 'videoCount': len(results), 'videoBytes': sum(item['bytes'] for item in results), 'videos': results, 'passed': True}
(ROOT / 'metadata/release-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'videoCount': len(results), 'allRemoteDigestsMatch': True, 'releaseUrl': remote['html_url']}, ensure_ascii=False), flush=True)
