(() => {
    const form = document.querySelector("#card-form[data-dictionary-url]");
    if (!form) return;

    const headwordInput = form.querySelector("#id_question");
    const translationInput = form.querySelector("#id_answer");
    const dictionaryEntryInput = form.querySelector("#id_dictionary_entry_id");
    if (!headwordInput || !translationInput) return;

    const suggestions = document.createElement("div");
    suggestions.className = "dictionary-suggestions";
    suggestions.id = "dictionary-suggestions";
    suggestions.setAttribute("role", "listbox");
    suggestions.hidden = true;
    headwordInput.insertAdjacentElement("afterend", suggestions);
    headwordInput.setAttribute("aria-autocomplete", "list");
    headwordInput.setAttribute("aria-controls", suggestions.id);
    headwordInput.setAttribute("aria-expanded", "false");

    let timer;
    let controller;
    let requestNumber = 0;

    const closeSuggestions = () => {
        suggestions.replaceChildren();
        suggestions.hidden = true;
        headwordInput.setAttribute("aria-expanded", "false");
    };

    const chooseSuggestion = (entry) => {
        headwordInput.value = entry.headword;
        translationInput.value = entry.translation;
        if (dictionaryEntryInput) dictionaryEntryInput.value = entry.id;
        translationInput.dispatchEvent(new Event("input", { bubbles: true }));
        closeSuggestions();
        headwordInput.focus();
    };

    const makeSuggestion = (entry) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dictionary-suggestion";
        button.setAttribute("role", "option");

        const headword = document.createElement("span");
        headword.className = "dictionary-headword";
        headword.textContent = entry.headword;

        const translation = document.createElement("span");
        translation.className = "dictionary-translation";
        translation.textContent = entry.vocalized_translation
            ? `${entry.translation} (${entry.vocalized_translation})`
            : entry.translation;

        button.append(headword, translation);
        button.addEventListener("click", () => chooseSuggestion(entry));
        return button;
    };

    headwordInput.addEventListener("input", () => {
        window.clearTimeout(timer);
        if (dictionaryEntryInput) dictionaryEntryInput.value = "";
        const query = headwordInput.value.trim();
        if (query.length < 2) {
            if (controller) controller.abort();
            closeSuggestions();
            return;
        }

        timer = window.setTimeout(async () => {
            if (controller) controller.abort();
            controller = new AbortController();
            const currentRequest = ++requestNumber;

            try {
                const response = await fetch(
                    `${form.dataset.dictionaryUrl}?q=${encodeURIComponent(query)}`,
                    { headers: { Accept: "application/json" }, signal: controller.signal },
                );
                if (!response.ok) throw new Error("Dictionary lookup failed");
                const data = await response.json();
                if (currentRequest !== requestNumber) return;

                suggestions.replaceChildren(...data.results.map(makeSuggestion));
                suggestions.hidden = data.results.length === 0;
                headwordInput.setAttribute("aria-expanded", String(!suggestions.hidden));
            } catch (error) {
                if (error.name !== "AbortError") closeSuggestions();
            }
        }, 180);
    });

    headwordInput.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" && !suggestions.hidden) {
            event.preventDefault();
            suggestions.querySelector("button")?.focus();
        } else if (event.key === "Escape") {
            closeSuggestions();
        }
    });

    form.addEventListener("focusout", (event) => {
        if (!form.contains(event.relatedTarget)) closeSuggestions();
    });
})();