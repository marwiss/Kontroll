// Copy-to-clipboard buttons: <button data-copy-target="id-of-element">.
// The value is read from the page (textContent), never from a script literal.
// Feedback texts come from data-t-* attributes on <html>, rendered in the page's language.

const texts = document.documentElement.dataset;

export function enhanceCopyButtons(root = document) {
  root.querySelectorAll("button[data-copy-target]").forEach((button) => {
    const target = document.getElementById(button.dataset.copyTarget);
    if (!target || !navigator.clipboard) {
      button.hidden = true;
      return;
    }
    const original = button.textContent;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(target.textContent.trim());
        button.textContent = texts.tCopied || "Copied";
      } catch {
        button.textContent = texts.tCopyFailed || "Copy failed";
      }
      setTimeout(() => {
        button.textContent = original;
      }, 2000);
    });
  });
}
