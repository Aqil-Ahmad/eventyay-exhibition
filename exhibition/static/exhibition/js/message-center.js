(function () {
    "use strict";

    function container() {
        return document.getElementById("email-list");
    }

    function load(url, push) {
        var target = container();
        if (!target) {
            return;
        }
        target.classList.add("email-list-loading");
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
            .then(function (response) {
                return response.text();
            })
            .then(function (html) {
                target.innerHTML = html;
                target.classList.remove("email-list-loading");
                target.dispatchEvent(
                    new CustomEvent("eventyay:ajax-results-replaced", { bubbles: true, detail: { container: target } })
                );
                if (push) {
                    window.history.pushState({ emailList: true }, "", url);
                }
            })
            .catch(function () {
                target.classList.remove("email-list-loading");
                window.location.href = url;
            });
    }

    function onSubmit(event) {
        var form = event.target;
        if (!form.matches || !form.matches("#email-list form[data-ajax]")) {
            return;
        }
        event.preventDefault();
        var params = new URLSearchParams(new FormData(form)).toString();
        load(window.location.pathname + "?" + params, true);
    }

    function onClick(event) {
        var link = event.target.closest("#email-list a[data-ajax], #email-list .btn-clear-filter");
        if (!link) {
            return;
        }
        event.preventDefault();
        load(link.href, true);
    }

    function onChange(event) {
        var element = event.target;
        if (element.matches("[data-select-all]")) {
            var rows = element.closest("table").querySelectorAll("[data-select-row]");
            rows.forEach(function (row) {
                row.checked = element.checked;
            });
        } else if (element.matches("[data-select-row]")) {
            var table = element.closest("table");
            var all = table.querySelector("[data-select-all]");
            if (all) {
                var boxes = Array.prototype.slice.call(table.querySelectorAll("[data-select-row]"));
                all.checked = boxes.length > 0 && boxes.every(function (box) {
                    return box.checked;
                });
            }
        }
    }

    document.addEventListener("submit", onSubmit);
    document.addEventListener("click", onClick);
    document.addEventListener("change", onChange);
    window.addEventListener("popstate", function () {
        if (container()) {
            load(window.location.href, false);
        }
    });
})();
