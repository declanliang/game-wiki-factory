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
const messagesMap: Record<string, unknown> = {
  en,
  es,
  de,
  fr,
  ja,
  ko,
};

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  // Never merge English at request time. The generation/build gates require
  // every locale to be complete so a localized URL cannot silently render an
  // English page and create duplicate-content or hreflang conflicts.
  const messages = messagesMap[locale] as Messages;

  return { locale, messages };
});
