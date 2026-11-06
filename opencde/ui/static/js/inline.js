// Forms marked data-inline save without leaving the page. The server answers as it does for any
// form, with a redirect to the page and a notice or with the page and an error, and that page's
// main element takes the old one's place, so the user sees what a reload would have shown. The
// server's escaping holds, since the page is parsed whole and nothing is built from its text.
// Whatever goes wrong, the form is sent the ordinary way, as it is without this script.

function focusOn(element) {
  element.tabIndex = -1;
  element.focus();
}

function sendTheOrdinaryWay(form, submitter) {
  form.removeAttribute("data-inline");
  form.requestSubmit(submitter ?? undefined);
}

async function save(form, submitter, onReplaced) {
  const fields = new FormData(form, submitter ?? undefined);
  // The attribute, since these forms have a field named "action", which is what form.action gives.
  const address = form.getAttribute("action") ?? location.href;
  // Nothing on the page can be pressed until the answer has replaced it, or a press would be lost with it.
  const main = document.querySelector("main");
  main.inert = true;
  try {
    const response = await fetch(address, { method: "POST", body: new URLSearchParams(fields) });
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    const fresh = page.querySelector("main");
    if (!fresh || new URL(response.url).pathname !== location.pathname) {
      location.assign(response.url); // signed out in another window, or another page altogether
      return;
    }
    main.replaceWith(fresh);
    document.title = page.title;
    if (response.redirected) history.replaceState(null, "", response.url);
    onReplaced(fresh);
    focusOn(fresh.querySelector(".alert") ?? fresh);
  } catch {
    main.inert = false;
    sendTheOrdinaryWay(form, submitter);
  }
}

export function enhanceInlineForms(onReplaced) {
  // On the document, so that it reaches forms in a replaced main element, and after a form's
  // own listeners, so that a confirmation dialog goes first.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || !form.matches("form[data-inline]")) return;
    event.preventDefault();
    save(form, event.submitter, onReplaced);
  });
}
