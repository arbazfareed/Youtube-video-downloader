function findPageMedia() {
  for (const element of document.querySelectorAll("video, audio")) {
    const candidates = [
      element.currentSrc,
      element.src,
      element.getAttribute("data-src"),
      element.getAttribute("data-url"),
    ];
    for (const source of element.querySelectorAll("source[src]")) {
      candidates.push(source.src);
      candidates.push(source.getAttribute("data-src"));
    }
    const url = candidates.find(value => {
      if (!value) return false;
      try {
        return ["http:", "https:"].includes(new URL(value, location.href).protocol);
      } catch {
        return false;
      }
    });
    if (url) {
      return new URL(url, location.href).href;
    }
  }
  for (const selector of [
    "meta[property='og:video']",
    "meta[property='og:video:url']",
    "meta[property='og:video:secure_url']",
    "meta[name='twitter:player:stream']",
  ]) {
    const meta = document.querySelector(selector);
    const content = meta?.getAttribute("content");
    if (content) {
      try {
        const parsed = new URL(content, location.href);
        if (["http:", "https:"].includes(parsed.protocol)) {
          return parsed.href;
        }
      } catch {}
    }
  }
  return null;
}

(globalThis.browser || globalThis.chrome).runtime.onMessage.addListener(message => {
  if (message?.type === "find-media") {
    return Promise.resolve({ url: findPageMedia() });
  }
  return undefined;
});
