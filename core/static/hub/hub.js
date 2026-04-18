(() => {
    const body = document.body;
    const selectAll = document.getElementById("select-all");
    const checks = Array.from(document.querySelectorAll(".feed-check"));
    const exportInput = document.getElementById("selected-feeds-input");
    const editInput = document.getElementById("selected-feeds-edit-input");
    const countNode = document.getElementById("selected-count");
    const bulkPanel = document.getElementById("bulk-mode-panel");
    const exportForm = document.getElementById("bulk-export-form");
    const editForm = document.getElementById("bulk-edit-form");
    const enterBulkMode = document.getElementById("enter-bulk-mode");
    const exitBulkMode = document.getElementById("exit-bulk-mode");
    const html = document.documentElement;
    const themeSelect = document.querySelector('.preference-form select[name="theme"]');
    const uiLanguage = (html.lang || "zh-hans").toLowerCase();
    const emptySelectionMessage =
        uiLanguage === "en-us"
            ? "Select at least one feed first."
            : "请先选择至少一个信源。";

    const syncSelection = () => {
        const selected = checks.filter((item) => item.checked).map((item) => item.value);
        const selectedValue = selected.join(",");
        exportInput.value = selectedValue;
        if (editInput) {
            editInput.value = selectedValue;
        }
        countNode.textContent = String(selected.length);
        if (selectAll) {
            selectAll.checked = checks.length > 0 && selected.length === checks.length;
        }
    };

    const enterMode = () => {
        body.classList.add("bulk-mode");
        if (bulkPanel) {
            bulkPanel.classList.remove("is-hidden");
        }
        if (enterBulkMode) {
            enterBulkMode.setAttribute("aria-expanded", "true");
        }
        syncSelection();
    };

    const exitMode = () => {
        body.classList.remove("bulk-mode");
        if (bulkPanel) {
            bulkPanel.classList.add("is-hidden");
        }
        if (enterBulkMode) {
            enterBulkMode.setAttribute("aria-expanded", "false");
        }
        checks.forEach((item) => {
            item.checked = false;
        });
        if (selectAll) {
            selectAll.checked = false;
        }
        syncSelection();
    };

    checks.forEach((item) => item.addEventListener("change", syncSelection));
    if (selectAll) {
        selectAll.addEventListener("change", () => {
            checks.forEach((item) => {
                item.checked = selectAll.checked;
            });
            syncSelection();
        });
    }

    if (enterBulkMode) {
        enterBulkMode.addEventListener("click", enterMode);
    }
    if (exitBulkMode) {
        exitBulkMode.addEventListener("click", exitMode);
    }

    if (themeSelect) {
        themeSelect.addEventListener("change", () => {
            html.dataset.theme = themeSelect.value || "system";
        });
    }

    if (exportInput && countNode && exportForm) {
        exportForm.addEventListener("submit", (event) => {
            syncSelection();
            if (!exportInput.value) {
                event.preventDefault();
                window.alert(emptySelectionMessage);
            }
        });

        if (editForm) {
            editForm.addEventListener("submit", (event) => {
                syncSelection();
                if (!exportInput.value) {
                    event.preventDefault();
                    window.alert(emptySelectionMessage);
                }
            });
        }

        syncSelection();
    }
})();
