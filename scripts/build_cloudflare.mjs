#!/usr/bin/env node
import { createReadStream } from 'node:fs';
import { copyFile, lstat, mkdir, mkdtemp, open, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const MAX_ASSET_BYTES = 25 * 1024 * 1024;
export const RELEASE_BASE = 'https://github.com/Brclio/xucen-english-learning/releases/download/course-v1/';
const CORE = ['index.html', 'app.js', 'styles.css', 'books.html', 'books.js', 'books.css', 'course-data.js', 'course-data.json', 'books-data.js', 'books-data.json'];
const DOCUMENTS = ['课程介绍.md', '课程目录.md', '绘本书目.md', '验收报告.md'];
const REPORTS = ['resource-audit', 'books-validation', 'books-browser-verification', 'browser-verification', 'archive-validation', 'original-source-deep-investigation', 'original-source-alternate-routes', 'original-source-provenance-samples'].map(name => `metadata/${name}.json`);
export function safeRelative(value) {
  if (typeof value !== 'string' || !value || value.includes('\\') || /[\u0000-\u001f\u007f?#%]/.test(value) || path.posix.isAbsolute(value) || value.split('/').some(part => !part || part.startsWith('.'))) throw new Error(`不安全的资源路径：${value}`);
  return value;
}
export async function sourceFile(root, relative) {
  safeRelative(relative);
  let current = root;
  for (const part of relative.split('/')) {
    current = path.join(current, part);
    if ((await lstat(current)).isSymbolicLink()) throw new Error(`不接受符号链接：${relative}`);
  }
  const info = await stat(current);
  if (!info.isFile()) throw new Error(`不是普通文件：${relative}`);
  const handle = await open(current, 'r');
  try {
    const buffer = Buffer.alloc(256);
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    if (buffer.subarray(0, bytesRead).toString('utf8').startsWith('version https://git-lfs.github.com/spec/v1')) throw new Error(`资源是 Git LFS 指针而非文件实体：${relative}。请恢复完整文件后重试。`);
  } finally { await handle.close(); }
  return { absolute: current, bytes: info.size, mtimeMs: info.mtimeMs };
}
export async function hashFile(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
async function readJson(file) { return JSON.parse(await readFile(file, 'utf8')); }
export function releaseVideoUrl(relative) {
  safeRelative(relative);
  const match = /^media\/videos\/(\d{2})_[^/]+\.mp4$/.exec(relative);
  if (!match) throw new Error(`视频路径不在预期目录或缺少课程序号：${relative}`);
  return RELEASE_BASE + `lesson-${match[1]}.mp4`;
}
function replaceExactly(source, before, after) {
  if (source.split(before).length !== 2) throw new Error(`在线版本适配锚点不唯一或缺失：${before.slice(0, 75)}`);
  return source.replace(before, after);
}
export function transformApp(source, allowedUrls) {
  replaceExactly(source, '  const localPath = value => {', '  const localPath = value => {');
  if (!Array.isArray(allowedUrls) || !allowedUrls.length || allowedUrls.some(url => typeof url !== 'string' || !url.startsWith(RELEASE_BASE) || !/^lesson-\d{2}\.mp4$/.test(url.slice(RELEASE_BASE.length)))) throw new Error('Release 视频白名单无效。');
  const anchor = '  const externalUrl = value =>';
  const inserted = `  const releaseVideoUrls = new Set(${JSON.stringify([...new Set(allowedUrls)])});\n  const mediaPath = value => {\n    const candidate = String(value || '').trim();\n    return releaseVideoUrls.has(candidate) ? candidate : localPath(candidate);\n  };\n`;
  let result = replaceExactly(source, anchor, inserted + anchor);
  const linkLine = source.split('\n').find(line => line.startsWith('  const link = '));
  if (!linkLine || !linkLine.includes('localPath(path)')) throw new Error('缺少媒体链接适配锚点。');
  result = replaceExactly(result, linkLine, linkLine.replaceAll('localPath(path)', 'mediaPath(path)'));
  for (const reference of ['localPath(lesson.videoPath)', 'localPath(l.videoPath)']) {
    if (!result.includes(reference)) throw new Error(`缺少播放器适配锚点：${reference}`);
    result = result.replaceAll(reference, reference.replace('localPath', 'mediaPath'));
  }
  const summaryLine = source.split('\n').find(line => line.trim().startsWith('const summaryMessage = '));
  if (!summaryLine) throw new Error('缺少在线资料说明适配锚点。');
  result = result.replaceAll('本地学习室', '在线学习室').replaceAll('本地视频', '在线视频').replaceAll('本地音频', '本站音频').replaceAll('本地资料状态', '在线资料状态');
  return replaceExactly(result, summaryLine, "    const summaryMessage = '在线视频来自公开 GitHub Release，播放需要联网；音频、图片和文字由本站提供。\\n' + (typeof data.summary?.message === 'string' ? data.summary.message.replace('已保存本地视频', '已归档完整视频') : '');");
}
function allowed(relative) {
  return CORE.includes(relative) || DOCUMENTS.includes(relative) || REPORTS.includes(relative) || relative === 'SHA256SUMS.txt' ||
    /^lessons\/[^/]+\.md$/.test(relative) ||
    /^media\/(?:images|book-covers)\/[^/]+\.(?:png|jpe?g|webp|gif|svg)$/i.test(relative) ||
    /^media\/audio\/[^/]+\.mp3$/.test(relative) ||
    /^metadata\/(?:original-quality-investigation|original-source-deep-investigation)\.md$/.test(relative) ||
    /^attachments\/(?!.*(?:^|\/)\.)[^?#%\\]+\.(?:pdf|md|txt|png|jpe?g|webp|gif|zip|docx?|pptx?|xlsx?)$/i.test(relative);
}
async function walk(root, folder) {
  const files = [];
  let entries;
  try { entries = await readdir(path.join(root, folder), { withFileTypes: true }); }
  catch (error) { if (error.code === 'ENOENT') return files; throw error; }
  for (const entry of entries) {
    const relative = `${folder}/${entry.name}`;
    if (entry.isSymbolicLink()) throw new Error(`构建不接受符号链接：${relative}`);
    if (entry.isDirectory()) files.push(...await walk(root, relative));
    else if (allowed(relative)) files.push(relative);
  }
  return files;
}
export function transformMarkdown(source, relative, videoUrls) {
  return source.replace(/(!?\[[^\]\n]*\]\()([^\n)]+)(\))/g, (match, before, target, after) => {
    if (/^(?:[a-z][a-z\d+.-]*:|#|\/\/)/i.test(target)) return match;
    let decoded;
    try { decoded = decodeURIComponent(target); } catch { throw new Error(`Markdown 链接编码无效：${relative}`); }
    const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(relative), decoded));
    if (videoUrls.has(resolved)) return before + videoUrls.get(resolved) + after;
    if (resolved.startsWith('media/videos/')) throw new Error(`Markdown 引用了未知视频：${relative} → ${target}`);
    return match;
  }).replaceAll('本地视频', '在线视频');
}
export async function build(root = ROOT) {
  const course = await readJson(path.join(root, 'course-data.json'));
  const books = await readJson(path.join(root, 'books-data.json'));
  if (!Array.isArray(course.lessons) || !course.lessons.length) throw new Error('课程目录为空。');
  const mapFile = await sourceFile(root, 'metadata/release-file-map.json');
  const releaseMap = await readJson(mapFile.absolute);
  if (releaseMap.releaseBase !== RELEASE_BASE || !Array.isArray(releaseMap.files) || releaseMap.files.length !== course.lessons.length) throw new Error('Release 映射数量或来源不匹配。');
  const mapping = new Map(releaseMap.files.map(item => [item.lessonId, item]));
  if (mapping.size !== course.lessons.length) throw new Error('Release 映射有重复课时。');
  const videoUrls = new Map();
  const audioPaths = new Set();
  const onlineCourse = structuredClone(course);
  for (const lesson of onlineCourse.lessons) {
    const originalPath = lesson.videoPath;
    const item = mapping.get(lesson.id);
    const url = releaseVideoUrl(originalPath);
    if (!item || item.originalPath !== originalPath || item.url !== url || item.assetName !== url.slice(RELEASE_BASE.length) || !Number.isSafeInteger(item.bytes) || item.bytes <= 0 || !/^[a-f0-9]{64}$/.test(item.sha256)) throw new Error(`Release 映射与课时不匹配：${lesson.id}`);
    if (videoUrls.has(originalPath)) throw new Error(`重复视频路径：${originalPath}`);
    videoUrls.set(originalPath, url);
    lesson.videoPath = url;
    if (!/^media\/audio\/[^/]+\.mp3$/.test(safeRelative(lesson.audioPath))) throw new Error(`无效音频路径：${lesson.audioPath}`);
    if (audioPaths.has(lesson.audioPath)) throw new Error(`重复音频路径：${lesson.audioPath}`);
    audioPaths.add(lesson.audioPath);
  }
  // MP4 files and their source splits are deliberately never read or restored here.
  const files = new Set([...CORE, ...DOCUMENTS, ...audioPaths]);
  for (const folder of ['lessons', 'media/images', 'media/book-covers', 'attachments', 'metadata']) for (const file of await walk(root, folder)) files.add(file);
  try { await sourceFile(root, 'SHA256SUMS.txt'); files.add('SHA256SUMS.txt'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const addReference = value => {
    if (!value) return;
    const relative = safeRelative(value);
    if (!allowed(relative)) throw new Error(`页面引用未在静态资源白名单中：${relative}`);
    files.add(relative);
  };
  addReference(course.cover);
  for (const item of course.attachments || []) addReference(item.path);
  for (const lesson of course.lessons) {
    addReference(lesson.markdownPath); addReference(lesson.poster);
    for (const item of lesson.attachments || []) addReference(item.path);
  }
  for (const book of books.books || []) addReference(book.cover);
  let audioManifest;
  try { audioManifest = await readJson(path.join(root, 'metadata/assets-manifest.json')); }
  catch (error) { if (error.code === 'ENOENT') throw new Error('缺少音频完整性清单 metadata/assets-manifest.json。'); throw error; }
  const expectedAudio = new Map(Object.values(audioManifest?.lessons || {}).filter(item => item.audio?.path).map(item => [item.audio.path, item.audio]));
  const validated = [];
  for (const relative of [...files].sort()) {
    const source = await sourceFile(root, relative);
    if (source.bytes > MAX_ASSET_BYTES) throw new Error(`静态资源超过 25 MiB：${relative}（${source.bytes} bytes）。原文件未作改动。`);
    if (audioPaths.has(relative)) {
      if (!source.bytes) throw new Error(`音频文件为空：${relative}`);
      const expected = expectedAudio.get(relative);
      if (!expected || !Number.isSafeInteger(expected.bytes) || expected.bytes <= 0 || !/^[a-f0-9]{64}$/.test(expected.sha256 || '')) throw new Error(`音频完整性清单缺少有效大小或 SHA-256：${relative}`);
      if (expected.bytes !== source.bytes) throw new Error(`音频大小与归档清单不符：${relative}`);
      if (expected.sha256 !== await hashFile(source.absolute)) throw new Error(`音频 SHA-256 与归档清单不符：${relative}`);
    }
    validated.push({ path: relative, ...source });
  }
  const privateDir = path.join(root, '.private');
  await mkdir(privateDir, { recursive: true });
  const stage = await mkdtemp(path.join(privateDir, 'pages-build-'));
  try {
    const reportFiles = [];
    for (const file of validated) {
      const target = path.join(stage, file.path);
      await mkdir(path.dirname(target), { recursive: true });
      if (file.path === 'course-data.json') await writeFile(target, JSON.stringify(onlineCourse, null, 2) + '\n');
      else if (file.path === 'course-data.js') await writeFile(target, 'window.COURSE_DATA = ' + JSON.stringify(onlineCourse, null, 2) + ';\n');
      else if (file.path === 'app.js') await writeFile(target, transformApp(await readFile(file.absolute, 'utf8'), [...videoUrls.values()]));
      else if (file.path.endsWith('.md')) await writeFile(target, transformMarkdown(await readFile(file.absolute, 'utf8'), file.path, videoUrls));
      else if (file.path.endsWith('.html')) await writeFile(target, (await readFile(file.absolute, 'utf8')).replaceAll('本地学习室', '在线学习室').replaceAll('本地课程库', '在线课程库').replaceAll('可离线学习', '可在线学习').replace('封面保存在本地，断网也可以翻看。', '封面和书目由本站提供，点击时码可跳转课程视频。'));
      else await copyFile(file.absolute, target);
      const info = await stat(target);
      if (info.size > MAX_ASSET_BYTES) throw new Error(`生成的静态资源超过 25 MiB：${file.path}`);
      reportFiles.push({ path: file.path, bytes: info.size, sha256: await hashFile(target) });
    }
    const headers = "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' https://github.com https://*.githubusercontent.com; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'\n";
    await writeFile(path.join(stage, '_headers'), headers);
    reportFiles.push({ path: '_headers', bytes: Buffer.byteLength(headers), sha256: createHash('sha256').update(headers).digest('hex') });
    const notFound = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>页面未找到</title><body><h1>页面未找到</h1><p><a href="/index.html">返回课程学习室</a></p></body></html>\n';
    await writeFile(path.join(stage, '404.html'), notFound);
    reportFiles.push({ path: '404.html', bytes: Buffer.byteLength(notFound), sha256: createHash('sha256').update(notFound).digest('hex') });
    const dist = path.join(root, 'dist');
    try { if ((await lstat(dist)).isSymbolicLink()) throw new Error('dist 是符号链接，拒绝覆盖。'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    await rm(dist, { recursive: true, force: true });
    await rename(stage, dist);
    const report = {
      updatedAt: new Date().toISOString(), mode: 'cloudflare-pages-static', releaseBase: RELEASE_BASE,
      staticFileCount: reportFiles.length, staticBytes: reportFiles.reduce((sum, file) => sum + file.bytes, 0),
      maximumAssetBytes: Math.max(...reportFiles.map(file => file.bytes)), videoCount: videoUrls.size, audioCount: audioPaths.size,
      sourceFilesChanged: false, videoFilesRead: false, videoFilesCopiedToDist: false,
      videos: [...videoUrls].map(([path, url]) => ({ path, url })), files: reportFiles,
    };
    await writeFile(path.join(privateDir, 'pages-build-report.json'), JSON.stringify(report, null, 2) + '\n', { mode: 0o600 });
    console.log(`Pages 静态包：${report.staticFileCount} 个文件，${report.staticBytes} bytes；最大单文件 ${report.maximumAssetBytes} bytes。`);
    console.log(`${report.videoCount} 个完整视频链接到公开 Release；${report.audioCount} 个 MP3 原样保留在静态包。构建未读取、还原或改写任何视频。`);
    return report;
  } finally { await rm(stage, { recursive: true, force: true }); }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) build().catch(error => { console.error(`构建失败：${error.message}`); process.exitCode = 1; });
