const SEARCH_DELAY_MS = 300

const form = document.querySelector('[data-exhibition-search]')
const results = document.querySelector('[data-exhibition-results]')

if (form && results) {
    let controller = null
    let timer = null

    const searchUrl = () => {
        const params = new URLSearchParams(new FormData(form))
        if (!params.get('query')) {
            params.delete('query')
        }
        const query = params.toString()
        return query ? `${window.location.pathname}?${query}` : window.location.pathname
    }

    const search = async () => {
        const url = searchUrl()
        controller?.abort()
        controller = new AbortController()
        results.setAttribute('aria-busy', 'true')
        try {
            const response = await fetch(url, { signal: controller.signal })
            const page = new DOMParser().parseFromString(await response.text(), 'text/html')
            const nextResults = page.querySelector('[data-exhibition-results]')
            if (!response.ok || !nextResults) {
                window.location.assign(url)
                return
            }
            results.replaceChildren(...nextResults.childNodes)
            window.history.replaceState(null, '', url)
            results.removeAttribute('aria-busy')
        } catch (error) {
            if (error.name !== 'AbortError') {
                window.location.assign(url)
            }
        }
    }

    form.addEventListener('submit', (event) => {
        event.preventDefault()
        window.clearTimeout(timer)
        search()
    })

    form.querySelector('input[name="query"]')?.addEventListener('input', () => {
        window.clearTimeout(timer)
        timer = window.setTimeout(search, SEARCH_DELAY_MS)
    })
}
