(function () {
  const enhanced = new WeakSet();

  function shouldSkip(select) {
    return !select ||
      enhanced.has(select) ||
      select.dataset.nativeSelect === 'true' ||
      select.closest('[data-native-select="true"]') ||
      select.disabled && select.options.length <= 1;
  }

  function enhance(select) {
    if (shouldSkip(select) || typeof window.Choices !== 'function') return;
    select.dataset.paiDropdown = 'choices';

    const optionsCount = select.options ? select.options.length : 0;
    const isTiny = optionsCount <= 4;
    const containerOuter = ['choices', 'pai-choices'];
    if (isTiny) containerOuter.push('pai-choices-compact');

    try {
      new window.Choices(select, {
        allowHTML: false,
        searchEnabled: optionsCount > 8,
        shouldSort: false,
        itemSelectText: '',
        removeItemButton: select.multiple,
        duplicateItemsAllowed: false,
        placeholder: true,
        searchPlaceholderValue: 'Tìm nhanh...',
        noResultsText: 'Không có kết quả',
        noChoicesText: 'Không còn lựa chọn',
        classNames: {
          containerOuter,
        },
      });
      enhanced.add(select);
    } catch (err) {
      delete select.dataset.paiDropdown;
      console.warn('[PAI dropdown] Không thể khởi tạo select:', err);
    }
  }

  function enhanceAll(root) {
    if (typeof window.Choices !== 'function') return;
    (root || document).querySelectorAll('select').forEach(enhance);
  }

  window.PAIEnhanceDropdowns = enhanceAll;

  function boot() {
    enhanceAll(document);

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          if (node.matches('select')) enhance(node);
          enhanceAll(node);
        });
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
