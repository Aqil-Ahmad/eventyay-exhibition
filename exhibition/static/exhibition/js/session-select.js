function checkedBoxes(grid) {
    return Array.from(grid.querySelectorAll('input[type="checkbox"]')).filter((box) => box.checked);
}

function initSessionSelect(widget) {
    if (widget.dataset.sessionSelectInit === 'true') {
        return;
    }
    const badges = widget.querySelector('[data-language-grid-badges]');
    const grid = widget.querySelector('[data-language-grid-grid]');
    if (!badges || !grid) {
        return;
    }
    widget.dataset.sessionSelectInit = 'true';

    badges.addEventListener('click', (event) => {
        const badge = event.target.closest('.language-grid-badge');
        if (!badge) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();

        const index = Array.from(badges.querySelectorAll('.language-grid-badge')).indexOf(badge);
        const target = checkedBoxes(grid)[index];
        if (target) {
            target.checked = false;
            target.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
}

function initAll() {
    document.querySelectorAll('.exhibition-session-select').forEach(initSessionSelect);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
} else {
    initAll();
}
