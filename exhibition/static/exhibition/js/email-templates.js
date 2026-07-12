(function () {
    function getCookie(name) {
        var cookieValue = null
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';')
            for (var index = 0; index < cookies.length; index++) {
                var cookie = cookies[index].trim()
                if (cookie.substring(0, name.length + 1) === name + '=') {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
                    break
                }
            }
        }
        return cookieValue
    }

    function initTemplatePreview(form) {
        var previewUrl = form.getAttribute('data-preview-url')
        if (!previewUrl) {
            return
        }

        form.querySelectorAll('.preview-panel').forEach(function (panel) {
            var role = panel.getAttribute('data-role')
            var previewTab = panel.querySelector('[data-template-preview-tab]')
            var previewGroup = panel.querySelector('.mail-preview-group')
            if (!role || !previewTab || !previewGroup) {
                return
            }
            var blocks = previewGroup.querySelectorAll('.mail-preview')

            function renderPreview() {
                var params = new URLSearchParams()
                params.append('role', role)
                panel.querySelectorAll('input[name], textarea[name]').forEach(function (input) {
                    params.append(input.name, input.value)
                })

                fetch(previewUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('eventyay_csrftoken') || getCookie('csrftoken'),
                    },
                    credentials: 'include',
                    body: params,
                })
                    .then(function (response) {
                        if (!response.ok) {
                            throw new Error('preview failed')
                        }
                        return response.json()
                    })
                    .then(function (data) {
                        var previews = data.previews || {}
                        blocks.forEach(function (block) {
                            block.innerHTML = previews[block.getAttribute('lang')] || ''
                        })
                        if (window.$) {
                            $(previewGroup).find('.placeholder').tooltip()
                        }
                    })
                    .catch(function () {
                        blocks.forEach(function (block) {
                            block.textContent = gettext('The preview could not be loaded. Please try again.')
                        })
                    })
            }

            $(previewTab).on('shown.bs.tab', renderPreview)
        })
    }

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.querySelector('form[data-preview-url]')
        if (form) {
            initTemplatePreview(form)
        }
    })
})()
