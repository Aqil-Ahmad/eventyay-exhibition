(function () {
    function init() {
        var scope = document.querySelector('[data-partner-select-scope]')
        if (!scope) {
            return
        }

        if (window.jQuery) {
            $(scope).find('[data-toggle="tooltip"]').tooltip()
        }

        var selectAll = scope.querySelector('[data-partner-select-all]')
        var countLabel = scope.querySelector('[data-partner-selected-count]')
        var downloadLink = scope.querySelector('[data-partner-download-link]')
        var sendButton = scope.querySelector('[data-partner-send-vouchers]')
        var sendForm = sendButton ? document.getElementById(sendButton.getAttribute('form')) : null
        var selectedLabel = scope.dataset.selectedLabel || 'selected'
        var baseHref = downloadLink ? downloadLink.getAttribute('href') : null
        var store = window.ExhibitionSelection.create({ scope: scope })

        function checkboxes() {
            return Array.prototype.slice.call(scope.querySelectorAll('[data-partner-checkbox]'))
        }

        function selectableIds() {
            return (
                store.available() ||
                checkboxes().map(function (box) {
                    return box.value
                })
            )
        }

        function refreshSelection() {
            checkboxes().forEach(function (box) {
                box.checked = store.has(box.value)
            })
            var total = store.size()
            var selectable = selectableIds().length
            if (countLabel) {
                countLabel.textContent = total ? total + ' ' + selectedLabel : ''
            }
            if (selectAll) {
                selectAll.checked = selectable > 0 && total === selectable
                selectAll.indeterminate = total > 0 && total < selectable
            }
            if (downloadLink) {
                downloadLink.classList.toggle('disabled', total === 0)
                downloadLink.setAttribute('aria-disabled', total === 0 ? 'true' : 'false')
            }
            if (sendButton) {
                sendButton.disabled = total === 0
            }
        }

        if (selectAll) {
            selectAll.addEventListener('change', function () {
                if (selectAll.checked) {
                    store.addAll(selectableIds())
                } else {
                    store.clear()
                }
                refreshSelection()
            })
        }

        scope.addEventListener('change', function (event) {
            if (event.target.hasAttribute('data-partner-checkbox')) {
                store.toggle(event.target.value, event.target.checked)
                refreshSelection()
            }
        })

        if (downloadLink && baseHref) {
            downloadLink.addEventListener('click', function (event) {
                event.preventDefault()
                var selected = store.ids()
                if (!selected.length) {
                    return
                }
                var searchParams = new URLSearchParams(window.location.search)
                searchParams.delete('pk')
                searchParams.set('download', 'yes')
                if (selected.length !== selectableIds().length) {
                    selected.forEach(function (value) {
                        searchParams.append('pk', value)
                    })
                }
                window.location.href = window.location.pathname + '?' + searchParams.toString()
            })
        }

        if (sendForm) {
            sendForm.addEventListener('submit', function (event) {
                var selected = store.ids()
                if (!selected.length) {
                    event.preventDefault()
                    return
                }
                sendForm.querySelectorAll('input[name="selected"]').forEach(function (input) {
                    input.remove()
                })
                selected.forEach(function (value) {
                    var hidden = document.createElement('input')
                    hidden.type = 'hidden'
                    hidden.name = 'selected'
                    hidden.value = value
                    sendForm.appendChild(hidden)
                })
            })
        }

        refreshSelection()
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init)
    } else {
        init()
    }
    document.addEventListener('eventyay:ajax-results-replaced', init)
})()
