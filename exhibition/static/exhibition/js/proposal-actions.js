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

        var actionConfig = {
            approve: { icon: 'fa-check', cls: 'proposal-action-approve', variant: 'btn-success', label: i18n.labelApprove },
            reject: { icon: 'fa-times', cls: 'proposal-action-reject', variant: 'btn-danger', label: i18n.labelReject },
            withdraw: { icon: 'fa-undo', cls: 'proposal-action-withdraw', variant: '', label: i18n.labelWithdraw },
            reopen: { icon: 'fa-inbox', cls: 'proposal-action-reopen', variant: '', label: i18n.labelReopen },
        }

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

        function buildActionButton(action, code) {
            var config = actionConfig[action]
            if (!config) {
                return null
            }
            var button = document.createElement('button')
            button.type = 'button'
            button.className = 'btn btn-sm proposal-action-btn ' + config.cls + (config.variant ? ' ' + config.variant : '')
            button.setAttribute('data-proposal-action', action)
            button.setAttribute('data-proposal-code', code)
            if (config.label) {
                button.title = config.label
            }
            var icon = document.createElement('i')
            icon.className = 'fa ' + config.icon
            button.appendChild(icon)
            return button
        }

        function rebuildActions(row, result) {
            var actionsCell = row.querySelector('[data-proposal-actions-cell]')
            if (!actionsCell) {
                return
            }
            actionsCell.querySelectorAll('[data-proposal-action]').forEach(function (button) {
                button.remove()
            })
            var viewLink = actionsCell.querySelector('a')
            ;(result.actions || []).forEach(function (action) {
                var button = buildActionButton(action, result.code)
                if (button) {
                    actionsCell.insertBefore(button, viewLink)
                }
            })
        }

        function rebuildCheckbox(row, result) {
            var cell = row.querySelector('[data-proposal-select-cell]')
            if (!cell) {
                return
            }
            var existing = cell.querySelector('[data-proposal-checkbox]')
            if (result.bulk_selectable && !existing) {
                var box = document.createElement('input')
                box.type = 'checkbox'
                box.className = 'proposal-select'
                box.value = result.code
                box.setAttribute('data-proposal-checkbox', '')
                if (i18n.selectAria) {
                    box.setAttribute('aria-label', i18n.selectAria)
                }
                cell.appendChild(box)
            } else if (!result.bulk_selectable && existing) {
                existing.remove()
            }
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
            rebuildActions(row, result)
            rebuildCheckbox(row, result)
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
            if (action === 'reopen') {
                return i18n.confirmReopenOne
            }
            return null
        }

        function confirmClassFor(action) {
            if (action === 'approve') {
                return 'btn-success'
            }
            if (action === 'reopen') {
                return 'btn-primary'
            }
            return 'btn-danger'
        }

        function requestConfirmation(action, message) {
            if (!message) {
                return Promise.resolve(true)
            }
            var options = {
                message: message,
                title: i18n.confirmTitle,
                confirmLabel: i18n.confirmLabel,
                cancelLabel: i18n.cancelLabel,
                confirmClass: confirmClassFor(action),
            }
            if (typeof window.showConfirmDialog === 'function') {
                return window.showConfirmDialog(options)
            }
            return Promise.resolve(window.confirm(message))
        }

        container.addEventListener('click', function (event) {
            var button = event.target.closest('[data-proposal-action]')
            if (!button) {
                return
            }
            var action = button.dataset.proposalAction
            var code = button.dataset.proposalCode
            requestConfirmation(action, confirmFor(action, false)).then(function (confirmed) {
                if (confirmed) {
                    submitAction(action, [code])
                }
            })
        })

        bulkButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var action = button.dataset.proposalBulk
                var codes = selectedCodes()
                if (!codes.length) {
                    return
                }
                requestConfirmation(action, confirmFor(action, true)).then(function (confirmed) {
                    if (confirmed) {
                        submitAction(action, codes)
                    }
                })
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
