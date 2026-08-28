import { randomUUID } from 'node:crypto';

import { put } from '@vercel/blob';

const CURRENT_RELEASE = 'windows-x64-0.1.1';

const RELEASES = Object.freeze({
  [CURRENT_RELEASE]: Object.freeze({
    version: '0.1.1',
    platform: 'windows-x64',
    fileName: 'fig-agent-0.1.1-x64-setup.exe',
    url: 'https://fig-agent-1439976580.cos.ap-hongkong.myqcloud.com/fig-agent-0.1.1-x64-setup.exe',
  }),
  'windows-x64-0.1.0': Object.freeze({
    version: '0.1.0',
    platform: 'windows-x64',
    fileName: 'fig-agent-0.1.0-x64-setup.exe',
    url: 'https://fig-agent-1439976580.cos.ap-hongkong.myqcloud.com/fig-agent-0.1.0-x64-setup.exe',
  }),
});

function firstQueryValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

function chinaDate(date) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

function respond(response, status, body) {
  response.statusCode = status;
  response.setHeader('Cache-Control', 'private, no-store');
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

function redirect(response, url) {
  response.statusCode = 302;
  response.setHeader('Cache-Control', 'private, no-store');
  response.setHeader('Location', url);
  response.setHeader('X-Robots-Tag', 'noindex, nofollow');
  response.end();
}

export function createDownloadHandler({
  writeEvent = put,
  now = () => new Date(),
  createId = randomUUID,
} = {}) {
  return async function downloadHandler(request, response) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.setHeader('Allow', 'GET, HEAD');
      return respond(response, 405, { ok: false, message: '仅支持下载安装包。' });
    }

    const releaseKey = firstQueryValue(request.query?.release) || CURRENT_RELEASE;
    const release = RELEASES[releaseKey];
    if (!release) {
      return respond(response, 404, { ok: false, message: '没有找到这个安装包版本。' });
    }

    if (request.method === 'GET') {
      const downloadedAt = now();
      const id = createId();
      const record = {
        schemaVersion: '1.0',
        id,
        downloadedAt: downloadedAt.toISOString(),
        version: release.version,
        platform: release.platform,
        fileName: release.fileName,
      };
      const datePrefix = chinaDate(downloadedAt);

      try {
        await writeEvent(
          `downloads/${datePrefix}/${release.version}/${release.platform}/${id}.json`,
          JSON.stringify(record),
          {
            access: 'private',
            addRandomSuffix: false,
            contentType: 'application/json; charset=utf-8',
          },
        );
      } catch (error) {
        console.error('Download event could not be recorded:', error?.message || 'unknown error');
      }
    }

    return redirect(response, release.url);
  };
}

export default createDownloadHandler();
