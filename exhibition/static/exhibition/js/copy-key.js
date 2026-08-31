(function () {
    function init() {
        document.querySelectorAll('.exhibitor-copy-key:not([data-copy-key-bound])').forEach(function (button) {
            button.setAttribute('data-copy-key-bound', 'true')
            var $button = $(button)
            var originalTitle = $button.attr('data-original-title') || button.getAttribute('title')

            function showFeedback(label) {
                $button.attr('data-original-title', label).tooltip('show')
                window.setTimeout(function () {
                    $button.tooltip('hide')
                    $button.attr('data-original-title', originalTitle)
                }, 2000)
            }

            button.addEventListener('click', function () {
                button.disabled = true
                fetch(button.dataset.url, { credentials: 'same-origin', cache: 'no-store' })
                    .then(function (response) {
                        if (!response.ok) {
                            throw new Error('Could not fetch exhibitor key.')
                        }
                        return response.json()
                    })
                    .then(function (data) {
                        return navigator.clipboard.writeText(data.key)
                    })
                    .then(function () {
                        showFeedback(button.dataset.copiedLabel)
                    })
                    .catch(function () {
                        showFeedback(button.dataset.failedLabel)
                    })
                    .finally(function () {
                        button.disabled = false
                    })
            })
        })
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init)
    } else {
        init()
    }
    document.addEventListener('eventyay:ajax-results-replaced', init)
})()
