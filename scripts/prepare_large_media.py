"""Store >100 MiB media as lossless 95 MiB ordinary-Git parts; retain originals."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART_SIZE = 95 * 1024 * 1024
out = ROOT / 'media/video-parts'
out.mkdir(parents=True, exist_ok=True)
files = []
for path in sorted((ROOT / 'media/videos').glob('*.mp4')):
    if path.stat().st_size <= 100 * 1024 * 1024:
        continue
    full = hashlib.sha256()
    parts = []
    with path.open('rb') as source:
        index = 1
        while chunk := source.read(PART_SIZE):
            full.update(chunk)
            target = out / f'{path.name}.part{index:03}'
            expected = hashlib.sha256(chunk).hexdigest()
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                temporary = target.with_suffix(target.suffix + '.tmp')
                temporary.write_bytes(chunk)
                temporary.replace(target)
            parts.append({'path': target.relative_to(ROOT).as_posix(), 'bytes': len(chunk), 'sha256': expected})
            index += 1
    files.append({'originalPath': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': full.hexdigest(), 'parts': parts})
manifest = {'version': 1, 'format': 'raw-byte-concatenation', 'partSize': PART_SIZE, 'files': files}
(ROOT / 'media/large-files.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'originalsUnchanged': True, 'largeVideos': len(files), 'parts': sum(len(f['parts']) for f in files), 'bytes': sum(f['bytes'] for f in files)}, ensure_ascii=False))
