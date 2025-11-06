import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = dirname(fileURLToPath(import.meta.url));
const base64Path = resolve(currentDir, '../public/favicon.ico.base64');
const outputPath = resolve(currentDir, '../public/favicon.ico');

try {
  const base64 = readFileSync(base64Path, 'utf8').trim();
  const buffer = Buffer.from(base64, 'base64');
  writeFileSync(outputPath, buffer);
  console.log(`Generated favicon.ico (${buffer.length} bytes)`);
} catch (error) {
  console.error('Failed to generate favicon.ico:', error);
  process.exit(1);
}

