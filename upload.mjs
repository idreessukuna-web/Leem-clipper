// Usage: node upload.mjs <dir> <jobId> [--delete-input]
// Uploads every file in <dir> to Vercel Blob under jobs/<jobId>/.
// JSON files go last, so manifest.json only appears once all clips are up.
import { put, del } from '@vercel/blob';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const [dir, jobId, flag] = process.argv.slice(2);
if (!dir || !jobId) {
  console.error('Usage: node upload.mjs <dir> <jobId> [--delete-input]');
  process.exit(1);
}

const rank = (f) => (f.endsWith('.json') ? 1 : 0);
const files = readdirSync(dir).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));

for (const f of files) {
  const contentType = f.endsWith('.json') ? 'application/json' : 'video/mp4';
  await put(`jobs/${jobId}/${f}`, readFileSync(join(dir, f)), {
    access: 'public',
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType,
  });
  console.log('uploaded', f);
}

if (flag === '--delete-input' && process.env.VIDEO_URL) {
  try {
    await del(process.env.VIDEO_URL);
    console.log('deleted original upload');
  } catch (e) {
    // Cleanup must never turn a finished job into a failed one.
    console.warn('could not delete original upload:', e.message);
  }
}
