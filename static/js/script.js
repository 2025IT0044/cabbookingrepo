(() => {
    const storageKey = "ridego_tab_id";
    let tabId = sessionStorage.getItem(storageKey);

    if (!tabId) {
        if (window.crypto && crypto.randomUUID) {
            tabId = crypto.randomUUID();
        } else {
            tabId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        }
        sessionStorage.setItem(storageKey, tabId);
    }

    const loginForm = document.querySelector("form[action$=\"/login\"], form:not([action])");
    if (loginForm && document.querySelector('input[name="role"]')) {
        let input = loginForm.querySelector('input[name="tab_id"]');
        if (!input) {
            input = document.createElement("input");
            input.type = "hidden";
            input.name = "tab_id";
            loginForm.appendChild(input);
        }
        input.value = tabId;
    }

    const currentUrl = new URL(window.location.href);
    if (currentUrl.pathname !== "/login" && !currentUrl.searchParams.has("tab_id")) {
        currentUrl.searchParams.set("tab_id", tabId);
        window.history.replaceState({}, "", currentUrl);
    }

    document.querySelectorAll("a[href], form[action]").forEach((element) => {
        const attribute = element.hasAttribute("href") ? "href" : "action";
        const rawUrl = element.getAttribute(attribute);
        if (!rawUrl || rawUrl.startsWith("#") || rawUrl.startsWith("mailto:")) return;

        const target = new URL(rawUrl, window.location.origin);
        if (target.origin !== window.location.origin) return;
        target.searchParams.set("tab_id", tabId);
        element.setAttribute(attribute, `${target.pathname}${target.search}${target.hash}`);
    });
})();
