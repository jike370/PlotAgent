import { readFile } from 'node:fs/promises';
import { URL } from 'node:url';

import { list } from '@vercel/blob';

async function loadLocalEnvironment() {
  if (process.env.BLOB_READ_WRITE_TOKEN) return;

  try {
    const source = await readFile(new URL('../.env.local', import.meta.url), 'utf8');
    for (const line of source.split(/\r?\n/)) {
      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      if (!match || process.env[match[1]]) continue;
      process.env[match[1]] = match[2].replace(/^['"]|['"]$/g, '');
    }
  } catch {
    // The explicit error below explains how to make the token available.
  }
}

function chinaDate(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

await loadLocalEnvironment();

if (!process.env.BLOB_READ_WRITE_TOKEN) {
  throw new Error('缺少 BLOB_READ_WRITE_TOKEN。请先运行 vercel env pull .env.local。');
}

const pathnames = [];
let cursor;

do {
  const page = await list({
    prefix: 'downloads/',
    limit: 1000,
    cursor,
    token: process.env.BLOB_READ_WRITE_TOKEN,
  });
  pathnames.push(...page.blobs.map((blob) => blob.pathname));
  cursor = page.hasMore ? page.cursor : undefined;
} while (cursor);

const byDate = new Map();
const byVersion = new Map();

for (const pathname of pathnames) {
  const [, date, version] = pathname.split('/');
  if (!date || !version) continue;
  byDate.set(date, (byDate.get(date) || 0) + 1);
  byVersion.set(version, (byVersion.get(version) || 0) + 1);
}

const today = chinaDate();
const recentDates = [...byDate.entries()].sort(([a], [b]) => b.localeCompare(a)).slice(0, 7);

console.log(`累计下载发起：${pathnames.length}`);
console.log(`今日下载发起：${byDate.get(today) || 0}`);

if (byVersion.size > 0) {
  console.log('\n按版本：');
  for (const [version, count] of [...byVersion.entries()].sort()) {
    console.log(`  ${version}: ${count}`);
  }
}

if (recentDates.length > 0) {
  console.log('\n最近有下载的日期：');
  for (const [date, count] of recentDates) {
    console.log(`  ${date}: ${count}`);
  }
}
