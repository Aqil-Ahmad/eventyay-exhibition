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

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.querySelector('[data-proposal-list]')
        if (!container) {
            return
        }

        var actionUrl = container.dataset.proposalActionsUrl
        var csrfToken = getCookie('eventyay_csrftoken') || getCookie('csrftoken')
        var feedback = document.querySelector('[data-proposal-feedback]')
        var i18nEl = document.querySelector('[data-proposal-i18n]')
        var i18n = i18nEl ? i18nEl.dataset : {}

        var selectAll = container.querySelector('[data-proposal-select-all]')
        var bulkButtons = container.querySelectorAll('[data-proposal-bulk]')
        var countLabel = container.querySelector('[data-proposal-selected-count]')

        function checkboxes() {
            return Array.prototype.slice.call(container.querySelectorAll('[data-proposal-checkbox]'))
        }

        function selectedCodes() {
            return checkboxes()
                .filter(function (box) {
                    return box.checked
                })
                .map(function (box) {
                    return box.value
                })
        }

        function refreshSelection() {
            var boxes = checkboxes()
            var selected = boxes.filter(function (box) {
                return box.checked
            })
            var count = selected.length
            bulkButtons.forEach(function (button) {
                button.disabled = count === 0
            })
            if (countLabel) {
                countLabel.textContent = count ? count + ' ' + (i18n.selected || '') : ''
            }
            if (selectAll) {
                selectAll.checked = boxes.length > 0 && count === boxes.length
                selectAll.indeterminate = count > 0 && count < boxes.length
            }
        }

        function showFeedback(ok, message) {
            if (!feedback) {
                return
            }
            feedback.innerHTML = ''
            var alert = document.createElement('div')
            alert.className = 'alert ' + (ok ? 'alert-success' : 'alert-danger')
            alert.textContent = message
            feedback.appendChild(alert)
        }

        function updateRow(result) {
            var row = container.querySelector('[data-proposal-row="' + result.code + '"]')
            if (!row) {
                return
            }
            var stateCell = row.querySelector('[data-proposal-state]')
            if (stateCell) {
                stateCell.textContent = result.state_display
            }
            var actionsCell = row.querySelector('[data-proposal-actions-cell]')
            if (actionsCell) {
                actionsCell.querySelectorAll('[data-proposal-action]').forEach(function (button) {
                    button.remove()
                })
            }
            var checkbox = row.querySelector('[data-proposal-checkbox]')
            if (checkbox) {
                checkbox.remove()
            }
        }

        function setBusy(busy) {
            bulkButtons.forEach(function (button) {
                button.disabled = busy || selectedCodes().length === 0
            })
            container.querySelectorAll('[data-proposal-action]').forEach(function (button) {
                button.disabled = busy
            })
        }

        function submitAction(action, codes) {
            if (!codes.length) {
                return
            }
            setBusy(true)
            var body = new URLSearchParams()
            body.append('action', action)
            codes.forEach(function (code) {
                body.append('proposal', code)
            })
            fetch(actionUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                credentials: 'include',
                body: body,
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data }
                    })
                })
                .then(function (payload) {
                    if (payload.ok && payload.data.ok) {
                        payload.data.results.forEach(updateRow)
                        showFeedback(true, payload.data.message)
                    } else {
                        showFeedback(false, payload.data.message || i18n.error)
                    }
                })
                .catch(function () {
                    showFeedback(false, i18n.error)
                })
                .finally(function () {
                    setBusy(false)
                    refreshSelection()
                })
        }

        function confirmFor(action, isBulk) {
            if (isBulk) {
                if (action === 'approve') {
                    return i18n.confirmApprove
                }
                if (action === 'reject') {
                    return i18n.confirmReject
                }
                return null
            }
            if (action === 'reject') {
                return i18n.confirmRejectOne
            }
            if (action === 'withdraw') {
                return i18n.confirmWithdrawOne
            }
            return null
        }

        container.addEventListener('click', function (event) {
            var button = event.target.closest('[data-proposal-action]')
            if (!button) {
                return
            }
            var action = button.dataset.proposalAction
            var code = button.dataset.proposalCode
            var message = confirmFor(action, false)
            if (message && !window.confirm(message)) {
                return
            }
            submitAction(action, [code])
        })

        bulkButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var action = button.dataset.proposalBulk
                var codes = selectedCodes()
                if (!codes.length) {
                    return
                }
                var message = confirmFor(action, true)
                if (message && !window.confirm(message)) {
                    return
                }
                submitAction(action, codes)
            })
        })

        if (selectAll) {
            selectAll.addEventListener('change', function () {
                checkboxes().forEach(function (box) {
                    box.checked = selectAll.checked
                })
                refreshSelection()
            })
        }

        container.addEventListener('change', function (event) {
            if (event.target.matches('[data-proposal-checkbox]')) {
                refreshSelection()
            }
        })

        refreshSelection()
    })
})()
