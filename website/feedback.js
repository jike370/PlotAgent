/* global document, fetch, FormData */

const feedbackForm = document.querySelector('[data-feedback-form]');

if (feedbackForm) {
  const openedAt = feedbackForm.elements.namedItem('openedAt');
  const submitButton = feedbackForm.querySelector('[data-feedback-submit]');
  const status = feedbackForm.querySelector('[data-feedback-status]');
  const success = document.querySelector('[data-feedback-success]');
  openedAt.value = String(Date.now());

  feedbackForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    status.textContent = '';

    if (!feedbackForm.reportValidity()) return;

    submitButton.disabled = true;
    submitButton.textContent = '正在提交…';

    const payload = Object.fromEntries(new FormData(feedbackForm).entries());
    payload.consent = payload.consent === 'on';

    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || result.ok !== true) throw new Error(result.message || '反馈暂时无法提交。');

      feedbackForm.hidden = true;
      success.hidden = false;
      success.focus();
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : '反馈暂时无法提交，请稍后重试。';
      submitButton.disabled = false;
      submitButton.textContent = '提交反馈';
    }
  });
}
