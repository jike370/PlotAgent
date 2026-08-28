import assert from 'node:assert/strict';
import test from 'node:test';

import { createDownloadHandler } from '../api/download.mjs';

function responseDouble() {
  const headers = new Map();
  return {
    headers,
    statusCode: 200,
    body: '',
    setHeader(name, value) {
      headers.set(name.toLowerCase(), value);
    },
    end(value = '') {
      this.body = value;
    },
  };
}

test('records a valid download before redirecting to COS', async () => {
  const writes = [];
  const handler = createDownloadHandler({
    writeEvent: async (...args) => writes.push(args),
    now: () => new Date('2026-08-28T13:00:00.000Z'),
    createId: () => 'event-1',
  });
  const response = responseDouble();

  await handler(
    { method: 'GET', query: { release: 'windows-x64-0.1.1' } },
    response,
  );

  assert.equal(response.statusCode, 302);
  assert.equal(
    response.headers.get('location'),
    'https://fig-agent-1439976580.cos.ap-hongkong.myqcloud.com/fig-agent-0.1.1-x64-setup.exe',
  );
  assert.equal(writes.length, 1);
  assert.equal(writes[0][0], 'downloads/2026-08-28/0.1.1/windows-x64/event-1.json');
  assert.deepEqual(JSON.parse(writes[0][1]), {
    schemaVersion: '1.0',
    id: 'event-1',
    downloadedAt: '2026-08-28T13:00:00.000Z',
    version: '0.1.1',
    platform: 'windows-x64',
    fileName: 'fig-agent-0.1.1-x64-setup.exe',
  });
  assert.equal(writes[0][2].access, 'private');
});

test('HEAD requests redirect without increasing the count', async () => {
  let writes = 0;
  const handler = createDownloadHandler({ writeEvent: async () => { writes += 1; } });
  const response = responseDouble();

  await handler({ method: 'HEAD', query: {} }, response);

  assert.equal(response.statusCode, 302);
  assert.equal(writes, 0);
});

test('unknown releases are rejected', async () => {
  const handler = createDownloadHandler({ writeEvent: async () => {} });
  const response = responseDouble();

  await handler({ method: 'GET', query: { release: 'unknown' } }, response);

  assert.equal(response.statusCode, 404);
  assert.match(response.body, /没有找到/);
});

test('a storage failure never blocks the download', async () => {
  const handler = createDownloadHandler({
    writeEvent: async () => { throw new Error('storage unavailable'); },
  });
  const response = responseDouble();

  await handler({ method: 'GET', query: {} }, response);

  assert.equal(response.statusCode, 302);
  assert.match(response.headers.get('location'), /fig-agent-0\.1\.1-x64-setup\.exe$/);
});
