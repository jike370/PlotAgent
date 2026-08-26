/* global setTimeout */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { JSDOM } from 'jsdom';

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const websiteRoot = path.join(repositoryRoot, 'website');

const html = fs.readFileSync(path.join(websiteRoot, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(websiteRoot, 'main.js'), 'utf8');
const manifest = JSON.parse(
  fs.readFileSync(
    path.join(websiteRoot, 'assets', 'templates', 'gallery', 'manifest.json'),
    'utf8',
  ),
);

const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

const run = async () => {
  assert(manifest.length === 34, 'template manifest must contain 34 chart profiles');

  const dom = new JSDOM(html, {
    url: 'http://127.0.0.1:8767/',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  const { window } = dom;

  window.fetch = async () => ({ ok: true, json: async () => manifest });
  window.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  });
  window.HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute('open', '');
  };
  window.HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute('open');
    this.dispatchEvent(new window.Event('close'));
  };

  window.eval(script);
  await new Promise((resolve) => setTimeout(resolve, 20));

  const cards = window.document.querySelectorAll('.template-card');
  assert(cards.length === 34, 'gallery must render 34 cards');
  assert(
    window.document.querySelector('[data-gallery-current]').textContent === 'Origin 原生图',
    'Origin must be the default gallery backend',
  );
  assert(
    window.document.querySelector('.template-card img').src.endsWith('-origin.webp'),
    'default cards must use Origin assets',
  );

  window.document.querySelector('[data-gallery-backend="matplotlib"]').click();
  assert(
    window.document.querySelector('[data-gallery-current]').textContent === 'Matplotlib 图',
    'global gallery toggle label did not update',
  );
  assert(
    [...window.document.querySelectorAll('.template-card img')].every((image) =>
      image.src.endsWith('-matplotlib.webp'),
    ),
    'global gallery toggle did not update every card',
  );

  window.document.querySelector('.template-card').click();
  const dialog = window.document.querySelector('[data-template-dialog]');
  assert(dialog.hasAttribute('open'), 'comparison dialog did not open');
  assert(
    dialog.querySelector('[data-dialog-origin]').src.endsWith('-origin.webp'),
    'comparison dialog is missing its Origin image',
  );
  assert(
    dialog.querySelector('[data-dialog-matplotlib]').src.endsWith('-matplotlib.webp'),
    'comparison dialog is missing its Matplotlib image',
  );
  dialog.querySelector('[data-dialog-close]').click();
  assert(!dialog.hasAttribute('open'), 'comparison dialog did not close');

  console.log('landing page interactions: PASS');
};

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
