/** Restore original MP4 bytes from ordinary-Git parts; never overwrite existing media. */
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { mkdir, readFile, stat, open, link, unlink } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const checkOnly = process.argv.includes('--check');
const manifest = JSON.parse(await readFile(path.join(root, 'media/large-files.json'), 'utf8'));
function local(relative) {
  const full = path.resolve(root, relative);
  if (!full.startsWith(root + path.sep)) throw new Error(`Unsafe manifest path: ${relative}`);
  return full;
}
async function fileDigest(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
for (const item of manifest.files) {
  const destination = local(item.originalPath);
  let existing;
  try { existing = await stat(destination); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (existing) {
    if (existing.size !== item.bytes || await fileDigest(destination) !== item.sha256) {
      throw new Error(`Existing video differs; left untouched: ${item.originalPath}`);
    }
  }
  const temporary = destination + `.restore-${process.pid}.tmp`;
  let output;
  const totalHash = createHash('sha256');
  let totalBytes = 0;
  try {
    if (!checkOnly && !existing) {
      await mkdir(path.dirname(destination), { recursive: true });
      output = await open(temporary, 'wx', 0o644);
    }
    for (const part of item.parts) {
      const source = local(part.path);
      const partHash = createHash('sha256');
      let partBytes = 0;
      for await (const chunk of createReadStream(source)) {
        partHash.update(chunk); totalHash.update(chunk);
        partBytes += chunk.length; totalBytes += chunk.length;
        if (output) {
          let offset = 0;
          while (offset < chunk.length) {
            const { bytesWritten } = await output.write(chunk, offset, chunk.length - offset);
            if (!bytesWritten) throw new Error('Unable to write restored video');
            offset += bytesWritten;
          }
        }
      }
      if (partBytes !== part.bytes || partHash.digest('hex') !== part.sha256) throw new Error(`Damaged part: ${part.path}`);
    }
    if (totalBytes !== item.bytes || totalHash.digest('hex') !== item.sha256) throw new Error(`Reassembly checksum mismatch: ${item.originalPath}`);
    if (output) {
      await output.sync(); await output.close(); output = null;
      // Hard-link creation is atomic and fails if an original appeared concurrently.
      await link(temporary, destination);
      await unlink(temporary);
    }
    console.log(`${existing ? 'Verified unchanged' : checkOnly ? 'Verified parts' : 'Restored'}: ${item.originalPath}`);
  } catch (error) {
    await output?.close().catch(() => {});
    await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; });
    throw error;
  }
}
console.log(`All ${manifest.files.length} large videos verified. No transcoding or original-file replacement.`);
