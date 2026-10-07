(function () {
    function init() {
        var dialog = document.getElementById('request-email-dialog')
        var trigger = document.querySelector('[data-request-email-open]')
        if (!dialog || !trigger || typeof dialog.showModal !== 'function') {
            return
        }

        trigger.addEventListener('click', function (event) {
            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
                return
            }
            event.preventDefault()
            dialog.showModal()
            var subject = dialog.querySelector('input[name="subject"]')
            if (subject) {
                subject.focus()
            }
        })

        dialog.querySelectorAll('[data-request-email-close]').forEach(function (button) {
            button.addEventListener('click', function () {
                dialog.close()
            })
        })

        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) {
                dialog.close()
            }
        })

        dialog.addEventListener('close', function () {
            trigger.focus()
        })
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init)
    } else {
        init()
    }
})()
