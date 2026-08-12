(function () {
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-schedule-fill-now]").forEach(function (button) {
            var input = document.getElementById(button.dataset.scheduleFillNow)
            if (!input) return

            var timeZone = input.dataset.eventTimezone
            if (!timeZone) return

            button.addEventListener("click", function () {
                input.value = formatNowInTimeZone(timeZone)
            })
        })
    })

    function formatNowInTimeZone(timeZone) {
        var parts = new Intl.DateTimeFormat("en-CA", {
            timeZone: timeZone,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
        }).formatToParts(new Date())

        var lookup = {}
        parts.forEach(function (part) {
            lookup[part.type] = part.value
        })

        return lookup.year + "-" + lookup.month + "-" + lookup.day + "T" + lookup.hour + ":" + lookup.minute
    }
})()
