// Confirmation dialogs for forms marked data-confirm="question". Without this
// script the form submits directly, which is acceptable because every such
// action is also protected server-side (form token, password confirmation).
// Button texts come from data-t-* attributes on <html>, rendered in the page's language.

const texts = document.documentElement.dataset;
let dialog;

function ensureDialog() {
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.className = "confirm";
  const heading = document.createElement("h2");
  heading.className = "confirm__title";
  heading.textContent = texts.tConfirmTitle || "Please confirm";
  const message = document.createElement("p");
  message.className = "confirm__message";
  const actions = document.createElement("div");
  actions.className = "cluster";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn btn--secondary";
  cancel.textContent = texts.tCancel || "Cancel";
  cancel.addEventListener("click", () => dialog.close("cancel"));
  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.className = "btn btn--danger";
  confirm.textContent = texts.tConfirm || "Confirm";
  confirm.addEventListener("click", () => dialog.close("confirm"));
  actions.append(cancel, confirm);
  dialog.append(heading, message, actions);
  document.body.appendChild(dialog);
  return dialog;
}

export function enhanceConfirmations(root = document) {
  root.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.confirmed === "yes") {
        form.dataset.confirmed = "";
        return;
      }
      event.preventDefault();
      const box = ensureDialog();
      box.querySelector(".confirm__message").textContent = form.dataset.confirm;
      box.addEventListener(
        "close",
        () => {
          if (box.returnValue === "confirm") {
            form.dataset.confirmed = "yes";
            form.requestSubmit();
          }
        },
        { once: true },
      );
      box.showModal();
    });
  });
}
