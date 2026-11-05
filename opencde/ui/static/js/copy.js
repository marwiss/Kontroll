// Copy-to-clipboard buttons: <button data-copy-target="id-of-element">.
// The value is read from the page (textContent), never from a script literal.

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
        button.textContent = "Copied";
      } catch {
        button.textContent = "Copy failed";
      }
      setTimeout(() => {
        button.textContent = original;
      }, 2000);
    });
  });
}
