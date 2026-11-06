// This file was generated with the assistance of an AI coding tool.
// The answer to a browser's check for a service worker's script, at any address. The server has no
// worker of its own, so this one was left by another app that once ran on the address, and it
// answers with old copies of the pages. It removes itself, what it saved, and reloads the windows.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.map((name) => caches.delete(name)));
      await self.registration.unregister();
      const open = await self.clients.matchAll({ type: "window" });
      await Promise.all(open.map((client) => client.navigate(client.url)));
    })(),
  ),
);
