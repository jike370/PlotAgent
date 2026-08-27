import { randomUUID } from 'node:crypto';

import { put } from '@vercel/blob';

const MAX_BODY_BYTES = 32 * 1024;
const MIN_DESCRIPTION_LENGTH = 20;
const MAX_DESCRIPTION_LENGTH = 4000;
const MAX_REPRODUCTION_LENGTH = 3000;
const SECRET_PATTERN = /(?:sk-[a-z0-9_-]{12,}|(?:api[_ -]?key|authorization|bearer|password|credential)\s*[:=]\s*\S{8,})/i;

const ENUMS = Object.freeze({
  category: new Set(['bug', 'compatibility', 'suggestion']),
  stage: new Set(['install', 'model', 'import', 'generate', 'export-image', 'export-opju', 'other']),
  windowsVersion: new Set(['windows-11', 'windows-10', 'other']),
  originVersion: new Set(['origin-2024', 'origin-2021-2023', 'other', 'not-installed']),
  modelProvider: new Set(['zhipu', 'deepseek', 'bailian', 'custom', 'local', 'not-configured']),
});

function respond(response, status, body) {
  response.setHeader('Cache-Control', 'no-store');
  return response.status(status).json(body);
}

function text(value, maxLength, { required = false } = {}) {
  if (typeof value !== 'string') {
    if (required) throw new Error('INVALID_FIELD');
    return '';
  }
  const normalized = value.trim();
  if ((required && normalized.length === 0) || normalized.length > maxLength) {
    throw new Error('INVALID_FIELD');
  }
  return normalized;
}

function enumValue(body, key) {
  const value = text(body[key], 40, { required: true });
  if (!ENUMS[key].has(value)) throw new Error('INVALID_FIELD');
  return value;
}

function parseBody(request) {
  if (request.body && typeof request.body === 'object' && !Buffer.isBuffer(request.body)) {
    return request.body;
  }
  if (typeof request.body === 'string') return JSON.parse(request.body);
  if (Buffer.isBuffer(request.body)) return JSON.parse(request.body.toString('utf8'));
  throw new Error('INVALID_BODY');
}

export default async function handler(request, response) {
  if (request.method !== 'POST') {
    response.setHeader('Allow', 'POST');
    return respond(response, 405, { ok: false, message: '仅支持提交反馈。' });
  }

  const contentType = String(request.headers['content-type'] || '');
  const contentLength = Number(request.headers['content-length'] || 0);
  if (!contentType.includes('application/json') || contentLength > MAX_BODY_BYTES) {
    return respond(response, 413, { ok: false, message: '反馈内容过长，请精简后重试。' });
  }

  const requestOrigin = String(request.headers.origin || '');
  if (
    requestOrigin &&
    requestOrigin !== 'https://fig-agent.cn' &&
    requestOrigin !== 'http://localhost:8000' &&
    !/^https:\/\/fig-agent-[a-z0-9-]+-cix4\.vercel\.app$/.test(requestOrigin)
  ) {
    return respond(response, 403, { ok: false, message: '无法从当前页面提交反馈。' });
  }

  try {
    const body = parseBody(request);
    if (JSON.stringify(body).length > MAX_BODY_BYTES) {
      return respond(response, 413, { ok: false, message: '反馈内容过长，请精简后重试。' });
    }

    // Honeypot submissions look successful so automated senders do not retry.
    if (text(body.company, 200)) return respond(response, 201, { ok: true });

    if (body.consent !== true) {
      return respond(response, 400, { ok: false, message: '请阅读并同意隐私说明后再提交。' });
    }

    const openedAt = Number(body.openedAt);
    const elapsed = Date.now() - openedAt;
    if (!Number.isFinite(openedAt) || elapsed < 1500 || elapsed > 24 * 60 * 60 * 1000) {
      return respond(response, 400, { ok: false, message: '页面停留时间异常，请刷新后重试。' });
    }

    const description = text(body.description, MAX_DESCRIPTION_LENGTH, { required: true });
    if (description.length < MIN_DESCRIPTION_LENGTH) {
      return respond(response, 400, { ok: false, message: '请再具体描述一下发生了什么。' });
    }

    const record = {
      schemaVersion: '1.0',
      id: randomUUID(),
      submittedAt: new Date().toISOString(),
      appVersion: text(body.appVersion, 32, { required: true }),
      category: enumValue(body, 'category'),
      stage: enumValue(body, 'stage'),
      windowsVersion: enumValue(body, 'windowsVersion'),
      originVersion: enumValue(body, 'originVersion'),
      modelProvider: enumValue(body, 'modelProvider'),
      description,
      reproduction: text(body.reproduction, MAX_REPRODUCTION_LENGTH),
      diagnosticId: text(body.diagnosticId, 120),
      contact: text(body.contact, 160),
    };

    const searchableText = [record.description, record.reproduction, record.diagnosticId, record.contact].join('\n');
    if (SECRET_PATTERN.test(searchableText)) {
      return respond(response, 400, {
        ok: false,
        message: '内容中可能包含 API Key、密码或凭据，请删除后再提交。',
      });
    }

    const datePrefix = record.submittedAt.slice(0, 10);
    await put(`feedback/${datePrefix}/${record.id}.json`, JSON.stringify(record, null, 2), {
      access: 'private',
      addRandomSuffix: false,
      contentType: 'application/json; charset=utf-8',
    });

    return respond(response, 201, { ok: true, feedbackId: record.id });
  } catch (error) {
    if (error instanceof SyntaxError || error?.message === 'INVALID_BODY' || error?.message === 'INVALID_FIELD') {
      return respond(response, 400, { ok: false, message: '请检查反馈字段后重试。' });
    }
    return respond(response, 500, { ok: false, message: '反馈暂时无法提交，请稍后重试或发送邮件。' });
  }
}
