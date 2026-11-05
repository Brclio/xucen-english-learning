"""Check offline book references, local cover bytes, and final document links."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

data = json.loads((ROOT / 'books-data.json').read_text())
course = json.loads((ROOT / 'course-data.json').read_text())
lessons = {l['id']: l for l in course['lessons']}
errors, covers, ids = [], {}, set()
for book in data['books']:
    if book['id'] in ids:
        errors.append('Duplicate book ID: ' + book['id'])
    ids.add(book['id'])
    for evidence in book.get('mentionEvidence', []):
        lesson = lessons.get(evidence.get('lessonId'))
        if not lesson:
            errors.append('Unknown lesson: ' + book['title'])
        elif isinstance(evidence.get('time'), (int, float)) and not 0 <= evidence['time'] <= lesson.get('duration', float('inf')):
            errors.append('Time outside lesson: ' + book['title'])
    if not book.get('mentionEvidence'):
        errors.append('Missing course evidence: ' + book['title'])
    if not book.get('cover'):
        continue
    path = ROOT / book['cover']
    if urlsplit(book['cover']).scheme or not path.is_file() or not path.resolve().is_relative_to(ROOT):
        errors.append('Missing or nonlocal cover: ' + book['title'])
        continue
    actual = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    expected = book.get('coverMetadata', {})
    for field in ('bytes', 'sha256'):
        if expected.get(field) and expected[field] != actual[field]:
            errors.append(f'Cover {field} mismatch: ' + book['title'])
    covers[book['cover']] = actual

for group in ('seriesMentions', 'uncertainMentions', 'otherReferences'):
    for entry in data.get(group, []):
        for evidence in entry.get('mentionEvidence', []):
            lesson = lessons.get(evidence.get('lessonId'))
            if not lesson:
                errors.append('Unknown reference lesson: ' + entry['title'])
            elif isinstance(evidence.get('time'), (int, float)) and not 0 <= evidence['time'] <= lesson.get('duration', float('inf')):
                errors.append('Reference time outside lesson: ' + entry['title'])

for filename, variable in [('books-data.js', 'BOOKS_DATA'), ('course-data.js', 'COURSE_DATA')]:
    source = (ROOT / filename).read_text()
    embedded = json.loads(source.removeprefix('window.' + variable + ' = ').rstrip().removesuffix(';').replace('<\\/', '</'))
    expected = data if variable == 'BOOKS_DATA' else course
    if embedded != expected:
        errors.append('JS and JSON disagree: ' + filename)

for path in list(ROOT.glob('*.md')) + list((ROOT / 'lessons').glob('*.md')) + [ROOT / 'metadata/original-source-deep-investigation.md']:
    for target in re.findall(r'\]\(([^\n]+?)\)', path.read_text()):
        parts = urlsplit(target)
        if parts.scheme or target.startswith('#'):
            continue
        if not (path.parent / unquote(parts.path)).exists():
            errors.append(f'Missing document link: {path.name}: {target}')

report = {
    'bookCount': sum(b.get('kind', 'book') == 'book' for b in data['books']),
    'seriesCount': sum(b.get('kind') == 'series' for b in data['books']) + len(data.get('seriesMentions', [])),
    'entryCount': len(data['books']),
    'coverCount': len(covers),
    'coverBytes': sum(c['bytes'] for c in covers.values()),
    'covers': covers,
    'uncertainMentions': len(data.get('uncertainMentions', [])),
    'otherReferences': len(data.get('otherReferences', [])),
    'errors': errors, 'complete': not errors,
}
(ROOT / 'metadata/books-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'covers'}, ensure_ascii=False))
if errors:
    raise SystemExit(1)

# Update the existing delivery fingerprint after new pages and covers are built.
files = [p for folder in ('media', 'lessons') for p in (ROOT / folder).rglob('*') if p.is_file() and not any(part.startswith('.') for part in p.relative_to(ROOT).parts)]
files += [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.html', '.css', '.js', '.json', '.md')]
(ROOT / 'SHA256SUMS.txt').write_text('\n'.join(f'{digest(p)}  {p.relative_to(ROOT)}' for p in sorted(files)) + '\n')
