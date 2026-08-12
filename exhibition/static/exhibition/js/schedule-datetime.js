(function () {
    document.addEventListener("DOMContentLoaded", function () {
        var input = document.querySelector("[data-schedule-datetime]")
        if (!input) return

        var timeZone = input.dataset.eventTimezone
        if (!timeZone) return

        input.addEventListener("focus", function () {
            if (!input.value) {
                input.value = formatNowInTimeZone(timeZone)
            }
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
