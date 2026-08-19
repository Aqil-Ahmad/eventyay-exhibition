(function () {
    "use strict";

    function init() {
        var variantField = document.querySelector("[data-question-variant]");
        var optionsGroup = document.querySelector("[data-question-options]");
        if (!variantField || !optionsGroup) {
            return;
        }

        var choiceVariants = (optionsGroup.dataset.choiceVariants || "").split(" ");

        function sync() {
            optionsGroup.hidden = choiceVariants.indexOf(variantField.value) === -1;
        }

        variantField.addEventListener("change", sync);
        sync();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
