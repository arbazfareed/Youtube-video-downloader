function findPageMedia() {
  for (const element of document.querySelectorAll("video, audio")) {
    const candidates = [element.currentSrc, element.src];
    for (const source of element.querySelectorAll("source[src]")) {
      candidates.push(source.src);
    }
    const url = candidates.find(value => {
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
  return null;
}

(globalThis.browser || globalThis.chrome).runtime.onMessage.addListener(message => {
  if (message?.type === "find-media") {
    return Promise.resolve({ url: findPageMedia() });
  }
  return undefined;
});
