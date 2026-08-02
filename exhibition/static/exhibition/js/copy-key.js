(function () {
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.exhibitor-copy-key').forEach(function (button) {
            button.addEventListener('click', function () {
                var originalLabel = button.getAttribute('title')

                button.disabled = true
                fetch(button.dataset.url, { credentials: 'same-origin' })
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
                        $(button).attr('data-original-title', button.dataset.copiedLabel).tooltip('show')
                    })
                    .catch(function () {
                        $(button).attr('data-original-title', button.dataset.failedLabel).tooltip('show')
                    })
                    .finally(function () {
                        button.disabled = false
                        window.setTimeout(function () {
                            $(button).attr('data-original-title', originalLabel)
                        }, 2000)
                    })
            })
        })
    })
})()
