import { useEffect } from "react";
import { Language } from "../i18n";
import { api, readStored, storeLocal } from "../services/api";

type TranslationResponse = { translations: string[] };
type Applied = { source: string; value: string; language: Language };
const attributes = ["placeholder", "aria-label", "title", "alt"] as const;

function hasTargetScript(value: string, language: Language) {
  const ranges: Partial<Record<Language, RegExp>> = {
    hi: /[\u0900-\u097F]/, mr: /[\u0900-\u097F]/, bn: /[\u0980-\u09FF]/,
    ta: /[\u0B80-\u0BFF]/, te: /[\u0C00-\u0C7F]/, kn: /[\u0C80-\u0CFF]/,
  };
  return ranges[language]?.test(value) ?? false;
}

function excluded(node: Node) {
  const element = node instanceof Element ? node : node.parentElement;
  return Boolean(element?.closest("input, textarea, select, script, style, code, .chat-message, [data-no-page-translate], .saved-report, .report-preview"));
}

export default function PageTranslator({ rootId, language }: { rootId: string; language: Language }) {
  useEffect(() => {
    const root = document.getElementById(rootId);
    if (!root || language === "en") return;
    let active = true;
    let scheduled = false;
    let requestId = 0;
    const textApplied = new Map<Text, Applied>();
    const attrApplied = new Map<Element, Map<string, Applied>>();
    const cacheKey = `page-translation-cache:${language}`;
    const cache = readStored<Record<string, string>>(cacheKey, {});

    const restore = () => {
      textApplied.forEach((entry, node) => { if (node.nodeValue === entry.value) node.nodeValue = entry.source; });
      attrApplied.forEach((entries, element) => entries.forEach((entry, name) => {
        if (element.getAttribute(name) === entry.value) element.setAttribute(name, entry.source);
      }));
    };

    const collect = () => {
      const pending = new Map<string, Array<{ node: Text | Element; attribute?: string }>>();
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let current: Node | null;
      while ((current = walker.nextNode())) {
        const node = current as Text;
        if (excluded(node)) continue;
        const prior = textApplied.get(node);
        const source = prior?.value === node.nodeValue && prior.language === language ? prior.source : (node.nodeValue || "");
        if (!source.trim() || source.trim().length < 2 || hasTargetScript(source, language)) continue;
        if (prior?.value === node.nodeValue && prior.language === language) continue;
        const list = pending.get(source) || [];
        list.push({ node }); pending.set(source, list);
      }
      root.querySelectorAll("[placeholder], [aria-label], [title], img[alt]").forEach(element => {
        if (excluded(element)) return;
        for (const name of attributes) {
          const value = element.getAttribute(name);
          if (!value || !value.trim() || hasTargetScript(value, language)) continue;
          const prior = attrApplied.get(element)?.get(name);
          const source = prior?.value === value && prior.language === language ? prior.source : value;
          if (prior?.value === value && prior.language === language) continue;
          const list = pending.get(source) || [];
          list.push({ node: element, attribute: name }); pending.set(source, list);
        }
      });
      return pending;
    };

    const translate = async () => {
      scheduled = false;
      if (!active) return;
      const thisRequest = ++requestId;
      const pending = collect();
      const uncached = [...pending.keys()].filter(text => !cache[text]);
      let start = 0;
      while (start < uncached.length) {
        const batch: string[] = [];
        let chars = 0;
        while (start < uncached.length && batch.length < 50 && chars + uncached[start].length <= 11000) {
          batch.push(uncached[start]); chars += uncached[start].length; start += 1;
        }
        if (!batch.length) { start += 1; continue; }
        try {
          const result = await api<TranslationResponse>("/advisor/translate-ui", { texts: batch, target: language }, { timeoutMs: 45000 });
          if (!active || thisRequest !== requestId || result.translations.length !== batch.length) return;
          batch.forEach((text, index) => { if (result.translations[index]?.trim()) cache[text] = result.translations[index]; });
          storeLocal(cacheKey, Object.fromEntries(Object.entries(cache).slice(-500)));
        } catch {
          // Keep the source text visible if Gemini or the network is unavailable.
        }
      }
      if (!active || thisRequest !== requestId) return;
      pending.forEach((targets, source) => {
        const value = cache[source];
        if (!value || value === source) return;
        targets.forEach(({ node, attribute }) => {
          if (node instanceof Text) {
            textApplied.set(node, { source, value, language }); node.nodeValue = value;
          } else if (node instanceof Element && attribute) {
            const entries = attrApplied.get(node) || new Map<string, Applied>();
            entries.set(attribute, { source, value, language }); attrApplied.set(node, entries); node.setAttribute(attribute, value);
          }
        });
      });
    };

    const schedule = () => { if (!scheduled) { scheduled = true; window.setTimeout(() => void translate(), 80); } };
    restore();
    const observer = new MutationObserver(schedule);
    observer.observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: [...attributes] });
    schedule();
    return () => { active = false; requestId += 1; observer.disconnect(); restore(); };
  }, [rootId, language]);
  return null;
}
