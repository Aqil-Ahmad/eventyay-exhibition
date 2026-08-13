(function () {
    var FILL_BUFFER_MINUTES = 2

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-schedule-datetime]").forEach(function (input) {
            var timeZone = input.dataset.eventTimezone
            if (!timeZone) return

            input.addEventListener("focus", function () {
                if (!input.value) {
                    input.value = formatNowInTimeZone(timeZone)
                }
            })
        })
    })

    function formatNowInTimeZone(timeZone) {
        var target = new Date(Date.now() + FILL_BUFFER_MINUTES * 60 * 1000)
        var parts = new Intl.DateTimeFormat("en-CA", {
            timeZone: timeZone,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
        }).formatToParts(target)

        var lookup = {}
        parts.forEach(function (part) {
            lookup[part.type] = part.value
        })

        return lookup.year + "-" + lookup.month + "-" + lookup.day + "T" + lookup.hour + ":" + lookup.minute
    }
})()
