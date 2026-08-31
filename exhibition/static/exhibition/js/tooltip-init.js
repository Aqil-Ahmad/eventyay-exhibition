(function () {
    "use strict";

    function initTooltips() {
        $('[data-toggle="tooltip"]').tooltip();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTooltips);
    } else {
        initTooltips();
    }
    document.addEventListener('eventyay:ajax-results-replaced', initTooltips);
})();
