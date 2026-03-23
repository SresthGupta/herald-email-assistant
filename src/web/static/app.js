// Herald - App JavaScript

// PWA install prompt
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  showInstallBanner();
});

function showInstallBanner() {
  const banner = document.getElementById('install-banner');
  if (banner) banner.classList.remove('hidden');
}

function installPWA() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(() => {
    deferredPrompt = null;
    const banner = document.getElementById('install-banner');
    if (banner) banner.remove();
  });
}

// HTMX loading indicator
document.addEventListener('htmx:beforeRequest', (e) => {
  const btn = e.detail.elt;
  if (btn && btn.tagName === 'BUTTON') {
    btn.dataset.originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `
      <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
    `;
  }
});

document.addEventListener('htmx:afterRequest', (e) => {
  const btn = e.detail.elt;
  if (btn && btn.dataset.originalText) {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.originalText;
    delete btn.dataset.originalText;
  }
});

// Add fade-in to HTMX swapped content
document.addEventListener('htmx:afterSwap', (e) => {
  if (e.detail.target) {
    e.detail.target.querySelectorAll(':scope > *').forEach(el => {
      el.classList.add('fade-in');
    });
  }
});

// Form loading states for regular form submits
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type="submit"]');
      if (btn && !btn.dataset.noLoading) {
        btn.disabled = true;
        btn.style.opacity = '0.7';
      }
    });
  });

  // Auto-dismiss flash messages
  setTimeout(() => {
    document.querySelectorAll('[data-auto-dismiss]').forEach(el => {
      el.style.transition = 'opacity 500ms';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    });
  }, 4000);
});

// Dark mode is always on (slate-950 background)
// We don't need a toggle since Herald is dark-only

// Keyboard shortcut: Cmd/Ctrl+K to focus chat
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
      chatInput.focus();
    } else {
      window.location.href = '/chat';
    }
  }
});

// Service worker registration for PWA
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {
      // SW registration failed, app still works
    });
  });
}
