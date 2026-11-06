// Kontroll has no service worker of its own, so a worker whose scope covers this page was left behind
// by another app that once ran on the same address. It answers with old copies of this server's pages,
// and their expired form tokens make the sign-in fail. Remove it and fetch the page again, once.
// This repairs an accident and protects nothing: a hostile worker can rewrite the page carrying this file.

const RELOADED = "opencde.foreign-worker-reloaded";

async function removeForeignWorkers() {
  if (!("serviceWorker" in navigator)) return;
  const registrations = await navigator.serviceWorker.getRegistrations();
  const covering = registrations.filter((registration) => location.href.startsWith(registration.scope));
  if (covering.length === 0) return;
  await Promise.all(covering.map((registration) => registration.unregister()));
  if (!navigator.serviceWorker.controller) return; // the network answered this page

  try {
    if (sessionStorage.getItem(RELOADED)) return;
    sessionStorage.setItem(RELOADED, "1");
  } catch {
    return; // with nowhere to remember the reload, it could repeat for ever
  }
  location.replace(location.href); // a plain GET: reload() would ask to send a form again
}

removeForeignWorkers().catch(() => {});
