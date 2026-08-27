/* global document, fetch */

const gallery = document.querySelector('[data-template-gallery]');
const backendButtons = Array.from(document.querySelectorAll('[data-gallery-backend]'));
const backendLabel = document.querySelector('[data-gallery-current]');
const dialog = document.querySelector('[data-template-dialog]');
let galleryItems = [];
let currentBackend = 'origin';
let lastGalleryTrigger = null;

const galleryImage = (profileId, backend) =>
  `/assets/templates/gallery/${profileId}-${backend}.webp`;

const fileName = (path) => String(path || '').split(/[\\/]/).pop();

const makeTemplateCard = (item) => {
  const card = document.createElement('button');
  card.className = 'template-card';
  card.type = 'button';
  card.dataset.profileId = item.profile_id;

  const media = document.createElement('span');
  media.className = 'template-card__media';

  const image = document.createElement('img');
  image.src = galleryImage(item.profile_id, currentBackend);
  image.width = 1024;
  image.height = 768;
  image.loading = 'lazy';
  image.alt = `${item.chinese_name}的${currentBackend === 'origin' ? 'Origin' : 'Matplotlib'}输出`;

  const badge = document.createElement('span');
  badge.className = 'template-card__backend';
  badge.textContent = currentBackend === 'origin' ? 'Origin' : 'Matplotlib';

  const content = document.createElement('span');
  content.className = 'template-card__content';
  const title = document.createElement('strong');
  title.textContent = `${item.profile_id} · ${item.chinese_name}`;
  const official = document.createElement('span');
  official.textContent = item.official_name;

  media.append(image, badge);
  content.append(title, official);
  card.append(media, content);
  card.addEventListener('click', () => openTemplateDialog(item, card));
  return card;
};

const renderGallery = () => {
  if (!gallery) return;
  const fragment = document.createDocumentFragment();
  for (const item of galleryItems) fragment.append(makeTemplateCard(item));
  gallery.replaceChildren(fragment);
};

const setBackend = (backend) => {
  currentBackend = backend;
  for (const button of backendButtons) {
    const active = button.dataset.galleryBackend === backend;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
  }
  if (backendLabel) {
    backendLabel.textContent = backend === 'origin' ? 'Origin 原生图' : 'Matplotlib 图';
  }
  renderGallery();
};

const openTemplateDialog = (item, trigger) => {
  if (!dialog) return;
  lastGalleryTrigger = trigger;
  dialog.querySelector('[data-dialog-profile]').textContent = item.profile_id;
  dialog.querySelector('[data-dialog-title]').textContent = item.chinese_name;
  dialog.querySelector('[data-dialog-official]').textContent = item.official_name;

  const originImage = dialog.querySelector('[data-dialog-origin]');
  originImage.src = galleryImage(item.profile_id, 'origin');
  originImage.alt = `${item.chinese_name}的 Origin 原生图`;

  const matplotlibImage = dialog.querySelector('[data-dialog-matplotlib]');
  matplotlibImage.src = galleryImage(item.profile_id, 'matplotlib');
  matplotlibImage.alt = `${item.chinese_name}的 Matplotlib 图`;

  const templates = (item.origin_templates || []).map((entry) => entry.filename).join('、');
  dialog.querySelector('[data-dialog-template]').textContent = `Origin 模板：${templates}`;
  dialog.querySelector('[data-dialog-sample]').textContent = `样例数据：${fileName(item.origin_sample)}`;
  const help = dialog.querySelector('[data-dialog-help]');
  help.href = item.official_help_url;
  dialog.showModal();
};

if (gallery) {
  fetch('/assets/templates/gallery/manifest.json')
    .then((response) => {
      if (!response.ok) throw new Error(`gallery manifest ${response.status}`);
      return response.json();
    })
    .then((items) => {
      galleryItems = items;
      renderGallery();
    })
    .catch(() => {
      gallery.innerHTML =
        '<p class="template-fallback">模板图库暂时无法载入，请稍后重试。</p>';
    });
}

for (const button of backendButtons) {
  button.addEventListener('click', () => setBackend(button.dataset.galleryBackend));
}

if (dialog) {
  dialog.querySelector('[data-dialog-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => lastGalleryTrigger?.focus());
}

for (const year of document.querySelectorAll('[data-current-year]')) {
  year.textContent = String(new Date().getFullYear());
}
