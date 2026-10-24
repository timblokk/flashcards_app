(() => {
    const form = document.querySelector(".auth-panel form[method='post']");
    const tokenInput = form?.querySelector("input[name='csrfmiddlewaretoken']");
    if (!form || !tokenInput) return;

    const refreshToken = () => {
        const cookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrftoken="));
        if (cookie) tokenInput.value = cookie.slice("csrftoken=".length);
    };

    window.addEventListener("pageshow", refreshToken);
    form.addEventListener("submit", refreshToken);
})();
