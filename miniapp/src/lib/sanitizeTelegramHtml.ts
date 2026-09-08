const ALLOWED_TAGS = new Set(["A", "B", "BR", "CODE", "EM", "I", "S", "STRONG", "U"]);

function sanitizeNode(node: Node, output: DocumentFragment): void {
  if (node.nodeType === Node.TEXT_NODE) {
    output.append(document.createTextNode(node.textContent ?? ""));
    return;
  }
  if (!(node instanceof HTMLElement)) return;

  if (!ALLOWED_TAGS.has(node.tagName)) {
    node.childNodes.forEach((child) => sanitizeNode(child, output));
    return;
  }

  const clean = document.createElement(node.tagName.toLowerCase());
  if (node.tagName === "A") {
    const rawHref = node.getAttribute("href");
    if (rawHref) {
      try {
        const href = new URL(rawHref, window.location.origin);
        if (href.protocol === "http:" || href.protocol === "https:") {
          clean.setAttribute("href", href.href);
          clean.setAttribute("target", "_blank");
          clean.setAttribute("rel", "noopener noreferrer");
        }
      } catch {
        // Invalid links are rendered as plain anchor text without navigation.
      }
    }
  }
  const children = document.createDocumentFragment();
  node.childNodes.forEach((child) => sanitizeNode(child, children));
  clean.append(children);
  output.append(clean);
}

export function sanitizeTelegramHtml(value: string): string {
  const parsed = new DOMParser().parseFromString(value, "text/html");
  const clean = document.createDocumentFragment();
  parsed.body.childNodes.forEach((node) => sanitizeNode(node, clean));
  const container = document.createElement("div");
  container.append(clean);
  return container.innerHTML;
}
