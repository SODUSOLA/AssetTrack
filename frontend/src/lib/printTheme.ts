/**
 * Paper is always light, whatever theme is on screen. The browser tells us when printing starts
 * and ends (the Print button and Ctrl+P both fire these), so the light theme is applied only for
 * the duration and the person's own choice is put back afterwards.
 */
export function installPrintTheme(target: Window = window): () => void {
  const root = target.document.documentElement;
  let before: string | null | undefined;

  const start = () => {
    if (before !== undefined) return;
    before = root.getAttribute("data-theme");
    root.setAttribute("data-theme", "light");
  };
  const end = () => {
    if (before === undefined) return;
    if (before === null) root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", before);
    before = undefined;
  };

  target.addEventListener("beforeprint", start);
  target.addEventListener("afterprint", end);
  return () => {
    target.removeEventListener("beforeprint", start);
    target.removeEventListener("afterprint", end);
    end();
  };
}
