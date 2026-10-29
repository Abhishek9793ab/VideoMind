
document.addEventListener("DOMContentLoaded", () => {
    // Automatically scroll the AI chat to the latest message.
    const chat = document.getElementById("chat");

    if (chat) {
        chat.scrollTop = chat.scrollHeight;

        const observer = new MutationObserver(() => {
            chat.scrollTop = chat.scrollHeight;
        });

        observer.observe(chat, {
            childList: true,
            subtree: true
        });
    }

    // Prevent accidental double submission of forms.
    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", () => {
            const submitButton = form.querySelector(
                'button[type="submit"], button:not([type])'
            );

            if (!submitButton || form.dataset.submitting === "true") {
                return;
            }

            form.dataset.submitting = "true";
            submitButton.disabled = true;
            submitButton.dataset.originalText =
                submitButton.textContent.trim();
            submitButton.textContent = "Please wait...";

            // Re-enable the button if the browser remains on this page.
            window.setTimeout(() => {
                if (document.body.contains(submitButton)) {
                    submitButton.disabled = false;
                    submitButton.textContent =
                        submitButton.dataset.originalText || "Submit";
                    form.dataset.submitting = "false";
                }
            }, 15000);
        });
    });

    // Copy content from any element with a data-copy-target attribute.
    document.querySelectorAll("[data-copy-target]").forEach((button) => {
        button.addEventListener("click", async () => {
            const target = document.querySelector(
                button.dataset.copyTarget
            );

            if (!target) return;

            const text = target.innerText || target.textContent || "";

            try {
                await navigator.clipboard.writeText(text);
                const original = button.textContent;
                button.textContent = "Copied!";
                window.setTimeout(() => {
                    button.textContent = original;
                }, 1500);
            } catch (error) {
                console.error("Unable to copy text:", error);
            }
        });
    });
});
