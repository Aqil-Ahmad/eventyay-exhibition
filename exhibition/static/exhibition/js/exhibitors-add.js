(function () {
    function setVisibleState(element, visible) {
        if (!element) return
        element.hidden = !visible
        element.style.display = visible ? '' : 'none'
    }

    var imageDialog = null

    function buildImageDialog() {
        var dialog = document.createElement('dialog')
        dialog.className = 'exhibition-image-dialog'
        dialog.setAttribute('role', 'alertdialog')
        dialog.innerHTML =
            '<div class="modal-card">' +
            '<div class="modal-card-content">' +
            '<figure class="text-center text-muted">' +
            '<img alt="">' +
            '<figcaption></figcaption>' +
            '</figure>' +
            '<button type="button" class="btn btn-default btn-xs exhibition-image-dialog-close">' +
            '<i class="fa fa-times"></i>' +
            '</button>' +
            '</div>' +
            '</div>'

        function close() {
            if (dialog.open) {
                dialog.close()
            }
            dialog.querySelector('img').removeAttribute('src')
        }

        dialog.addEventListener('click', close)
        dialog.querySelector('.modal-card-content').addEventListener('click', function (event) {
            event.stopPropagation()
        })
        dialog.querySelector('.exhibition-image-dialog-close').addEventListener('click', close)
        dialog.addEventListener('cancel', function () {
            dialog.querySelector('img').removeAttribute('src')
        })
        document.body.appendChild(dialog)
        return dialog
    }

    function openImageDialog(url, label) {
        if (!url) return
        if (!imageDialog) {
            imageDialog = buildImageDialog()
        }
        imageDialog.querySelector('img').src = url
        imageDialog.querySelector('img').alt = label || ''
        imageDialog.querySelector('figcaption').textContent = label || ''
        if (!imageDialog.open) {
            imageDialog.showModal()
        }
    }

    function initImageDialogTriggers() {
        document.addEventListener('click', function (event) {
            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
                return
            }
            if (!event.target || typeof event.target.closest !== 'function') {
                return
            }
            var link = event.target.closest('.exhibition-image-preview a[data-image-preview-link]')
            if (!link || !link.getAttribute('href')) {
                return
            }
            event.preventDefault()
            var image = link.querySelector('img')
            openImageDialog(link.href, image ? image.alt : '')
        })
    }

    document.addEventListener('DOMContentLoaded', function () {
        initImageDialogTriggers()
        var previewObjectUrls = new WeakMap()
        var sponsorCheckbox = document.getElementById('id_is_sponsor')
        var sponsorGroupWrapper = document.getElementById('sponsor-group-wrapper')
        var exhibitorCheckbox = document.getElementById('id_is_exhibitor')
        var boothNameWrapper = document.getElementById('booth-name-wrapper')
        var boothIdWrapper = document.getElementById('booth-id-wrapper')
        var leadScanningSection = document.getElementById('lead-scanning-section')
        var socialLinksFormset = document.getElementById('social-links-formset')
        var extraLinksFormset = document.getElementById('extra-links-formset')
        var socialLinkPrefixes = {}

        if (socialLinksFormset && socialLinksFormset.dataset.socialLinkPrefixes) {
            try {
                socialLinkPrefixes = JSON.parse(socialLinksFormset.dataset.socialLinkPrefixes)
            } catch (error) {
                socialLinkPrefixes = {}
            }
        }

        function revokePreviewObjectUrl(pair) {
            var url = previewObjectUrls.get(pair)
            if (url) {
                URL.revokeObjectURL(url)
                previewObjectUrls.delete(pair)
            }
        }

        function getImagePreviewSource(pair, fileInput, clearCheckbox) {
            if (fileInput.files && fileInput.files.length > 0) {
                revokePreviewObjectUrl(pair)
                var objectUrl = URL.createObjectURL(fileInput.files[0])
                previewObjectUrls.set(pair, objectUrl)
                return objectUrl
            }

            revokePreviewObjectUrl(pair)
            if (clearCheckbox && clearCheckbox.checked) {
                return ''
            }

            return pair.dataset.currentPreviewUrl || ''
        }

        function initImageSourcePair(pair) {
            var fileInput = document.getElementById(pair.dataset.fileInputId)
            var preview = pair.querySelector('[data-image-preview]')
            var previewLink = pair.querySelector('[data-image-preview-link]')
            var previewImage = pair.querySelector('[data-image-preview-image]')
            var previewError = pair.querySelector('[data-image-preview-error]')

            if (!fileInput || !preview || !previewLink || !previewImage) {
                return
            }

            var clearCheckbox = fileInput.form && fileInput.form.elements
                ? fileInput.form.elements[fileInput.name + '-clear']
                : null

            function syncImageState() {
                var previewSource = getImagePreviewSource(pair, fileInput, clearCheckbox)
                if (!previewSource) {
                    setVisibleState(preview, false)
                    setVisibleState(previewLink, false)
                    setVisibleState(previewImage, false)
                    setVisibleState(previewError, false)
                    previewLink.removeAttribute('href')
                    previewImage.removeAttribute('src')
                    return
                }

                setVisibleState(preview, true)
                setVisibleState(previewLink, true)
                previewLink.href = previewSource
                previewImage.src = previewSource
                setVisibleState(previewImage, true)
                setVisibleState(previewError, false)
            }

            previewImage.addEventListener('load', function () {
                setVisibleState(previewImage, true)
                setVisibleState(previewError, false)
            })
            previewImage.addEventListener('error', function () {
                if (!previewImage.src) {
                    return
                }
                setVisibleState(previewImage, false)
                setVisibleState(previewError, true)
            })

            fileInput.addEventListener('change', syncImageState)
            if (clearCheckbox) {
                clearCheckbox.addEventListener('change', function () {
                    if (clearCheckbox.checked) {
                        pair.dataset.hasCurrentFile = 'false'
                    }
                    syncImageState()
                })
            }

            syncImageState()
        }

        function updateSocialLinkPrefix(row) {
            if (!row) return
            var select = row.querySelector('select[name$="-network"]')
            var prefix = row.querySelector('[data-social-prefix]')
            if (!select || !prefix) {
                return
            }
            prefix.textContent = socialLinkPrefixes[select.value] || 'https://'
        }

        function initSocialLinkRow(row) {
            if (!row || row.dataset.socialPrefixBound === 'true') {
                updateSocialLinkPrefix(row)
                return
            }

            var select = row.querySelector('select[name$="-network"]')
            if (select) {
                select.addEventListener('change', function () {
                    updateSocialLinkPrefix(row)
                })
            }

            row.dataset.socialPrefixBound = 'true'
            updateSocialLinkPrefix(row)
        }

        function toggleSponsorGroup() {
            if (!sponsorCheckbox || !sponsorGroupWrapper) {
                return
            }
            sponsorGroupWrapper.classList.toggle('hidden', !sponsorCheckbox.checked)
        }

        function toggleExhibitorFields() {
            if (!exhibitorCheckbox) {
                return
            }
            var hideExhibitorFields = !exhibitorCheckbox.checked
            ;[boothNameWrapper, boothIdWrapper, leadScanningSection].forEach(function (element) {
                if (element) {
                    element.classList.toggle('hidden', hideExhibitorFields)
                }
            })
        }

        toggleSponsorGroup()
        toggleExhibitorFields()

        if (sponsorCheckbox) {
            sponsorCheckbox.addEventListener('change', toggleSponsorGroup)
        }

        if (exhibitorCheckbox) {
            exhibitorCheckbox.addEventListener('change', toggleExhibitorFields)
        }

        document.querySelectorAll('[data-partner-image-source-pair]').forEach(initImageSourcePair)
        document.querySelectorAll('[data-social-link-row]').forEach(initSocialLinkRow)

        if (window.jQuery) {
            if (socialLinksFormset) {
                var $socialLinksFormset = window.jQuery(socialLinksFormset)
                $socialLinksFormset.formset({
                    animateForms: true,
                    reorderMode: 'animate',
                    emptyForm: 'template[data-formset-empty-form]',
                })
                $socialLinksFormset.on('formAdded', 'div', function (event) {
                    initSocialLinkRow(event.target)
                })
            }

            if (extraLinksFormset) {
                window.jQuery(extraLinksFormset).formset({
                    animateForms: true,
                    reorderMode: 'animate',
                    emptyForm: 'template[data-formset-empty-form]',
                })
            }
        }
    })
})()
