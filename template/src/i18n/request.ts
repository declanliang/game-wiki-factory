import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

// --- Static imports of every locale's UI messages -------------------------
// When adding a language: add an import here AND an entry in `messagesMap`.
import en from "@/locales/en.json";
import es from "@/locales/es.json";
import de from "@/locales/de.json";
import fr from "@/locales/fr.json";
import ja from "@/locales/ja.json";
import ko from "@/locales/ko.json";

type Messages = typeof en;
type DeepPartial<T> = T extends Array<infer U>
  ? Array<DeepPartial<U>>
  : T extends object
    ? { [K in keyof T]?: DeepPartial<T[K]> }
    : T;

const messagesMap: Record<string, DeepPartial<Messages>> = {
  en,
  es,
  de,
  fr,
  ja,
  ko,
};

/**
 * Recursively merge `override` onto `base`. Missing keys in a non-English
 * locale automatically fall back to the English value, so a partial
 * translation never throws a missing-message error.
 */
function deepMerge<T>(base: T, override: DeepPartial<T>): T {
  if (
    typeof base !== "object" ||
    base === null ||
    typeof override !== "object" ||
    override === null
  ) {
    return (override as T) ?? base;
  }

  if (Array.isArray(base)) {
    return (Array.isArray(override) ? override : base) as T;
  }

  const result: Record<string, unknown> = { ...(base as Record<string, unknown>) };

  for (const key of Object.keys(override as Record<string, unknown>)) {
    const baseValue = (base as Record<string, unknown>)[key];
    const overrideValue = (override as Record<string, unknown>)[key];
    if (overrideValue === undefined) continue;
    result[key] = deepMerge(baseValue as never, overrideValue as never);
  }

  return result as T;
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  // Non-English locales are merged on top of English so untranslated keys
  // gracefully fall back instead of erroring.
  const messages = deepMerge(en, messagesMap[locale] ?? {});

  return { locale, messages };
});
