/* Copy the Cydia source URL. Everything else on the site works without JS. */
(function () {
  'use strict';

  function fallbackCopy(text, done) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', 'readonly');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    area.style.left = '-1000px';
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, text.length);
    try {
      document.execCommand('copy');
    } catch (ignore) {
      /* iOS 6 may refuse; the URL is still visible and selectable. */
    }
    document.body.removeChild(area);
    done();
  }

  function copyText(text, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallbackCopy(text, done);
      });
      return;
    }
    fallbackCopy(text, done);
  }

  var buttons = document.querySelectorAll('[data-copy]');
  var index;

  for (index = 0; index < buttons.length; index++) {
    buttons[index].addEventListener('click', function () {
      var button = this;
      var original = button.textContent;
      var text = button.getAttribute('data-copy');

      copyText(text, function () {
        button.textContent = 'Copied';
        window.setTimeout(function () {
          button.textContent = original;
        }, 1500);
      });
    });
  }
})();
