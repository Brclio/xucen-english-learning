import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { access, lstat, mkdir, mkdtemp, open, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { build, MAX_ASSET_BYTES, RELEASE_BASE, releaseVideoUrl, transformApp } from '../scripts/build_cloudflare.mjs';

const CORE = ['index.html', 'app.js', 'styles.css', 'books.html', 'books.js', 'books.css', 'course-data.js', 'course-data.json', 'books-data.js', 'books-data.json'];
const DOCUMENTS = ['课程介绍.md', '课程目录.md', '绘本书目.md', '验收报告.md'];
const VIDEO = "media/videos/00_中文 lesson (parent's).mp4";
const AUDIO = 'media/audio/01_本地音频.mp3';
const APP_SOURCE = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const sha256 = value => createHash('sha256').update(value).digest('hex');
const exists = async file => access(file).then(() => true, error => { if (error.code === 'ENOENT') return false; throw error; });

function mappedVideo(lessonId, originalPath) {
  const assetName = `lesson-${path.basename(originalPath).slice(0, 2)}.mp4`;
  return { lessonId, originalPath, assetName, url: RELEASE_BASE + assetName, bytes: 123, sha256: sha256('retained source video fixture') };
}

async function write(root, relative, value) {
  const target = path.join(root, relative);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, value);
}

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'course-pages-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const audio = Buffer.from('complete local audio fixture\x00mp3');
  const course = {
    title: '临时测试课程', cover: 'media/images/cover.jpg',
    attachments: [{ path: 'metadata/original-quality-investigation.md' }],
    lessons: [{ id: 'test-lesson', index: 1, title: '00_测试课', status: 'downloaded', videoPath: VIDEO, audioPath: AUDIO, poster: 'media/images/cover.jpg', markdownPath: 'lessons/01_测试课.md', attachments: [{ path: 'attachments/handout.pdf' }] }],
  };
  for (const name of CORE) await write(root, name, name.endsWith('.html') ? '<!doctype html><title>Fixture</title>' : `/* fixture ${name} */\n`);
  for (const name of DOCUMENTS) await write(root, name, `# ${name}\n\n临时验证文件。\n`);
  await write(root, 'app.js', APP_SOURCE);
  await write(root, 'course-data.json', JSON.stringify(course));
  await write(root, 'course-data.js', `window.COURSE_DATA = ${JSON.stringify(course)};\n`);
  await write(root, 'books-data.json', JSON.stringify({ books: [] }));
  await write(root, 'books-data.js', 'window.BOOKS_DATA = {"books": []};\n');
  await write(root, AUDIO, audio);
  await write(root, 'media/images/cover.jpg', Buffer.from('fixture cover jpg'));
  await write(root, 'media/book-covers/book.png', Buffer.from('fixture book png'));
  await write(root, 'lessons/01_测试课.md', '# 测试课\n');
  await write(root, 'attachments/handout.pdf', Buffer.from('%PDF-fixture'));
  await write(root, 'metadata/original-quality-investigation.md', '# 原画质说明\n');
  await write(root, 'metadata/assets-manifest.json', JSON.stringify({ lessons: { 'test-lesson': { audio: { path: AUDIO, bytes: audio.length, sha256: sha256(audio) } } } }));
  await write(root, 'metadata/release-file-map.json', JSON.stringify({ releaseBase: RELEASE_BASE, files: [mappedVideo('test-lesson', VIDEO)] }));
  return { root, audio, course };
}

async function tree(root, folder = '') {
  const files = [];
  for (const entry of await readdir(path.join(root, folder), { withFileTypes: true })) {
    const relative = folder ? `${folder}/${entry.name}` : entry.name;
    if (entry.isDirectory()) files.push(...await tree(root, relative));
    else files.push(relative);
  }
  return files.sort();
}

async function snapshot(root) {
  return Object.fromEntries(await Promise.all((await tree(root)).map(async relative => [relative, {
    bytes: await readFile(path.join(root, relative)), mtimeMs: (await lstat(path.join(root, relative))).mtimeMs,
  }])));
}

async function assertSourcesUnchanged(root, before) {
  for (const [relative, original] of Object.entries(before)) {
    assert.deepEqual(await readFile(path.join(root, relative)), original.bytes, `source changed: ${relative}`);
    assert.equal((await lstat(path.join(root, relative))).mtimeMs, original.mtimeMs, `source touched: ${relative}`);
  }
}

function pathFunctions(transformed) {
  // Execute the production helpers, stopping before the app's DOM/event setup.
  const end = transformed.indexOf('  const externalUrl =');
  assert.ok(end > 0, 'production externalUrl boundary must be present');
  return vm.runInNewContext(`${transformed.slice(0, end)}\nreturn { localPath, mediaPath, releaseVideoUrlsSet: releaseVideoUrls };\n})();`, {
    window: { COURSE_DATA: { lessons: [] } }, document: { querySelector() {} }, URL,
  });
}

test('Pages build succeeds without any local video and only transforms the deployment copy', async t => {
  const { root, course, audio } = await fixture(t);
  assert.equal(await exists(path.join(root, 'media/videos')), false);
  assert.equal(await exists(path.join(root, 'media/video-parts')), false);
  const before = await snapshot(root);
  await build(root);
  const deployed = JSON.parse(await readFile(path.join(root, 'dist/course-data.json'), 'utf8'));
  assert.equal(deployed.lessons[0].videoPath, RELEASE_BASE + 'lesson-00.mp4');
  assert.equal(deployed.lessons[0].audioPath, AUDIO);
  const expected = structuredClone(course);
  expected.lessons[0].videoPath = releaseVideoUrl(VIDEO);
  assert.deepEqual(deployed, expected);
  const context = { window: {} };
  vm.runInNewContext(await readFile(path.join(root, 'dist/course-data.js'), 'utf8'), context);
  assert.deepEqual(JSON.parse(JSON.stringify(context.window.COURSE_DATA)), expected);
  assert.deepEqual(await readFile(path.join(root, 'dist', AUDIO)), audio);
  const functions = pathFunctions(await readFile(path.join(root, 'dist/app.js'), 'utf8'));
  assert.equal(functions.mediaPath(deployed.lessons[0].videoPath), deployed.lessons[0].videoPath);
  await assertSourcesUnchanged(root, before);
  assert.equal(await exists(path.join(root, 'media/videos')), false);
});

test('Pages output keeps the public whitelist and excludes videos, parts, private data, and scripts', async t => {
  const { root } = await fixture(t);
  const excluded = ['.secret', '.dev.vars', '.private/token.json', '.git/config', 'scripts/internal.mjs', 'cloudflare/worker.js', VIDEO, 'media/video-parts/01.mp4.part001', 'media/images/run.js', 'metadata/private-response.json', 'metadata/assets-manifest.json', 'attachments/internal.json'];
  for (const relative of excluded) if (!(await exists(path.join(root, relative)))) await write(root, relative, 'retained source only');
  const before = await snapshot(root);
  await build(root);
  const output = await tree(path.join(root, 'dist'));
  for (const expected of [...CORE, ...DOCUMENTS, AUDIO, 'media/images/cover.jpg', 'media/book-covers/book.png', 'lessons/01_测试课.md', 'attachments/handout.pdf', 'metadata/original-quality-investigation.md']) assert.ok(output.includes(expected), `missing public asset: ${expected}`);
  for (const relative of excluded) assert.ok(!output.includes(relative), `private/source asset copied: ${relative}`);
  assert.ok(output.every(relative => !relative.endsWith('.mp4') && !relative.includes('video-parts') && !relative.startsWith('.') && !relative.includes('/.')));
  await assertSourcesUnchanged(root, before);
});

test('all 41 course videos receive exact Release URLs while every audio stays local', async t => {
  const { root, course, audio } = await fixture(t);
  const template = course.lessons[0];
  const manifest = { lessons: {} };
  const mapping = { releaseBase: RELEASE_BASE, files: [] };
  course.lessons = [];
  for (let index = 0; index < 41; index++) {
    const id = `lesson-${index + 1}`;
    const videoPath = index === 0 ? VIDEO : `media/videos/${String(index).padStart(2, '0')}_课程 (第 ${index + 1} 课).mp4`;
    const audioPath = index === 0 ? AUDIO : `media/audio/${String(index + 1).padStart(2, '0')}_课程.mp3`;
    course.lessons.push({ ...template, id, index: index + 1, videoPath, audioPath });
    mapping.files.push(mappedVideo(id, videoPath));
    await write(root, audioPath, audio);
    manifest.lessons[id] = { audio: { path: audioPath, bytes: audio.length, sha256: sha256(audio) } };
  }
  await write(root, 'course-data.json', JSON.stringify(course));
  await write(root, 'course-data.js', `window.COURSE_DATA = ${JSON.stringify(course)};\n`);
  await write(root, 'metadata/assets-manifest.json', JSON.stringify(manifest));
  // ID/path matching must work even when map order differs from course order.
  mapping.files.reverse();
  await write(root, 'metadata/release-file-map.json', JSON.stringify(mapping));
  await build(root);
  const deployed = JSON.parse(await readFile(path.join(root, 'dist/course-data.json'), 'utf8'));
  const functions = pathFunctions(await readFile(path.join(root, 'dist/app.js'), 'utf8'));
  assert.equal(deployed.lessons.length, 41);
  assert.equal(functions.releaseVideoUrlsSet.size, 41);
  for (let index = 0; index < 41; index++) {
    const expected = releaseVideoUrl(course.lessons[index].videoPath);
    assert.equal(deployed.lessons[index].videoPath, expected);
    assert.equal(functions.mediaPath(expected), expected);
    assert.equal(deployed.lessons[index].audioPath, course.lessons[index].audioPath);
    assert.deepEqual(await readFile(path.join(root, 'dist', deployed.lessons[index].audioPath)), audio);
  }
  assert.equal(await exists(path.join(root, 'media/videos')), false);
  assert.equal(await exists(path.join(root, 'dist/media/videos')), false);
});

test('release URLs use stable ASCII asset names despite Chinese, spaces, parentheses, and apostrophes in source names', () => {
  assert.equal(RELEASE_BASE, 'https://github.com/Brclio/xucen-english-learning/releases/download/course-v1/');
  for (const name of ['00_中文.mp4', '01_name with spaces.mp4', '02_(parentheses).mp4', "03_parent's book.mp4", '04_中文 (one two).mp4']) {
    assert.equal(releaseVideoUrl(`media/videos/${name}`), RELEASE_BASE + `lesson-${name.slice(0, 2)}.mp4`);
  }
});

test('a complete matching Release map is required before deployment', async t => {
  const { root } = await fixture(t);
  await rm(path.join(root, 'metadata/release-file-map.json'));
  await assert.rejects(build(root));
  assert.equal(await exists(path.join(root, 'dist')), false);
});

test('Release map rejects mismatched lesson IDs, source paths, asset names, and foreign URLs', async t => {
  const { root } = await fixture(t);
  const original = mappedVideo('test-lesson', VIDEO);
  const mutations = [
    { lessonId: 'unrelated-lesson' }, { originalPath: 'media/videos/99_other.mp4' },
    { assetName: 'lesson-99.mp4' }, { assetName: 'arbitrary.mp4', url: `${RELEASE_BASE}arbitrary.mp4` },
    { url: 'https://evil.example/lesson-00.mp4' }, { url: `${RELEASE_BASE}lesson-00.mp4?token=1` },
  ];
  for (const mutation of mutations) {
    await write(root, 'metadata/release-file-map.json', JSON.stringify({ releaseBase: RELEASE_BASE, files: [{ ...original, ...mutation }] }));
    await assert.rejects(build(root), undefined, `accepted invalid mapping ${JSON.stringify(mutation)}`);
    assert.equal(await exists(path.join(root, 'dist')), false);
  }
});

test('Release URL conversion rejects remote paths, traversal, encoded separators, and wrong media types', () => {
  for (const value of ['https://evil.example/video.mp4', '../video.mp4', 'media/videos/../video.mp4', 'media/videos/sub/video.mp4', 'media/videos/a%2fb.mp4', 'media/videos/a\\b.mp4', 'media/audio/audio.mp3', 'media/videos/video.mp4?token=1']) assert.throws(() => releaseVideoUrl(value), undefined, `accepted unsafe path ${value}`);
});

test('transformed production app allows only its exact Release URLs and preserves local-only helpers', () => {
  const allowed = [releaseVideoUrl(VIDEO), releaseVideoUrl('media/videos/02_另一课.mp4')];
  const transformed = transformApp(APP_SOURCE, allowed);
  assert.notEqual(transformed, APP_SOURCE);
  new vm.Script(transformed);
  const functions = pathFunctions(transformed);
  assert.equal(functions.releaseVideoUrlsSet.size, allowed.length);
  for (const url of allowed) {
    assert.equal(functions.releaseVideoUrlsSet.has(url), true);
    assert.equal(functions.mediaPath(url), url);
    assert.equal(functions.localPath(url), '');
  }
  for (const unknown of ['https://evil.example/remote.mp4', `${RELEASE_BASE}unknown.mp4`, `${allowed[0]}?download=1`, `${allowed[0]}#fragment`, '//github.com/Brclio/xucen-english-learning/releases/download/course-v1/test.mp4', 'javascript:alert(1)', 'data:video/mp4;base64,AAAA']) {
    assert.equal(functions.releaseVideoUrlsSet.has(unknown), false);
    assert.equal(functions.mediaPath(unknown), '', `unlisted remote accepted: ${unknown}`);
  }
  assert.equal(functions.mediaPath(AUDIO), AUDIO);
  assert.equal(functions.localPath('media/images/cover.jpg'), 'media/images/cover.jpg');
});

test('app transformation fails closed when required production anchors are absent', () => {
  const allowed = [releaseVideoUrl(VIDEO)];
  assert.throws(() => transformApp('/* missing app */', allowed));
  assert.throws(() => transformApp(APP_SOURCE.replace('const localPath =', 'const renamedPath ='), allowed));
});

test('an audio file larger than 25 MiB is rejected without damaging the previous build', async t => {
  const { root } = await fixture(t);
  const handle = await open(path.join(root, AUDIO), 'w');
  await handle.truncate(MAX_ASSET_BYTES + 1);
  await handle.close();
  const oversized = await readFile(path.join(root, AUDIO));
  await write(root, 'metadata/assets-manifest.json', JSON.stringify({ lessons: { 'test-lesson': { audio: { path: AUDIO, bytes: oversized.length, sha256: sha256(oversized) } } } }));
  await write(root, 'dist/previous.txt', 'previous complete deployment');
  await assert.rejects(build(root), /25\s*MiB/i);
  assert.equal((await lstat(path.join(root, AUDIO))).size, MAX_ASSET_BYTES + 1);
  assert.equal(await readFile(path.join(root, 'dist/previous.txt'), 'utf8'), 'previous complete deployment');
});

test('same-length corrupted audio is rejected using the manifest SHA-256', async t => {
  const { root, audio } = await fixture(t);
  const corrupted = Buffer.from(audio);
  corrupted[corrupted.length - 1] ^= 1;
  await write(root, AUDIO, corrupted);
  await assert.rejects(build(root), /SHA.?256|hash|校验/i);
  assert.equal(await exists(path.join(root, 'dist')), false);
  assert.deepEqual(await readFile(path.join(root, AUDIO)), corrupted);
});

test('audio length mismatch is rejected before it can reach Pages output', async t => {
  const { root, audio } = await fixture(t);
  await write(root, AUDIO, Buffer.concat([audio, Buffer.from('extra')]));
  await assert.rejects(build(root), /大小|bytes|size/i);
  assert.equal(await exists(path.join(root, 'dist')), false);
});

test('audio integrity requires a complete checksum manifest instead of silently skipping validation', async t => {
  const { root, audio } = await fixture(t);
  const manifestPath = 'metadata/assets-manifest.json';
  await rm(path.join(root, manifestPath));
  await assert.rejects(build(root));
  for (const audioRecord of [undefined, { path: AUDIO }, { path: AUDIO, bytes: audio.length }, { path: AUDIO, sha256: sha256(audio) }, { path: AUDIO, bytes: audio.length, sha256: 'not-a-hash' }]) {
    await write(root, manifestPath, JSON.stringify({ lessons: { 'test-lesson': audioRecord ? { audio: audioRecord } : {} } }));
    await assert.rejects(build(root), undefined, `accepted incomplete audio integrity metadata: ${JSON.stringify(audioRecord)}`);
  }
  assert.equal(await exists(path.join(root, 'dist')), false);
});

test('Git LFS audio pointer is rejected instead of being published as media', async t => {
  const { root } = await fixture(t);
  const pointer = 'version https://git-lfs.github.com/spec/v1\noid sha256:0123456789abcdef\nsize 500000\n';
  await write(root, AUDIO, pointer);
  await assert.rejects(build(root), /LFS|指针/);
  assert.equal(await exists(path.join(root, 'dist')), false);
  assert.equal(await readFile(path.join(root, AUDIO), 'utf8'), pointer);
});

test('missing local audio blocks deployment even though source videos are optional', async t => {
  const { root } = await fixture(t);
  await rm(path.join(root, AUDIO));
  await assert.rejects(build(root));
  assert.equal(await exists(path.join(root, 'dist')), false);
});

test('course audio paths cannot escape the public media/audio directory', async t => {
  const { root, course } = await fixture(t);
  for (const candidate of ['../private.mp3', '.private/secret.mp3', 'https://example.com/audio.mp3', 'media/audio/../private.mp3', 'media/audio/nested/audio.mp3', 'media/audio/a%2fb.mp3']) {
    course.lessons[0].audioPath = candidate;
    await write(root, 'course-data.json', JSON.stringify(course));
    await assert.rejects(build(root), undefined, `accepted unsafe audio path ${candidate}`);
    assert.equal(await exists(path.join(root, 'dist')), false);
  }
});

test('audio symlinks cannot import unrelated files into the public output', async t => {
  const { root, audio } = await fixture(t);
  await write(root, 'outside-secret.txt', audio);
  await rm(path.join(root, AUDIO));
  await symlink(path.join(root, 'outside-secret.txt'), path.join(root, AUDIO));
  await assert.rejects(build(root), /符号链接|symlink/i);
  assert.equal(await exists(path.join(root, 'dist')), false);
});

test('a course attachment cannot force private data into the static whitelist', async t => {
  const { root, course } = await fixture(t);
  course.attachments.push({ path: 'metadata/private-response.json' });
  await write(root, 'course-data.json', JSON.stringify(course));
  await write(root, 'metadata/private-response.json', 'private response');
  await assert.rejects(build(root), /白名单|allowlist/i);
  assert.equal(await exists(path.join(root, 'dist')), false);
});
