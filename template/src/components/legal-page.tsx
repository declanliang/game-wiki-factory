import type { Metadata } from "next";
import { getMessages } from "next-intl/server";
import { getSiteName, localizedSiteUrl } from "@/config/site";
import { languageAlternates, type Locale } from "@/i18n/routing";
import { localizeHref } from "@/lib/locale-path";
import { buildOpenGraph, buildTwitter } from "@/lib/seo";
import type en from "@/locales/en.json";

type Messages = typeof en;
export type LegalPageKey = keyof Messages["legal"];

const LEGAL_PATHS: Record<LegalPageKey, string> = {
  about: "/about",
  copyright: "/copyright",
  privacyPolicy: "/privacy-policy",
  termsOfService: "/terms-of-service",
};

export async function buildLegalMetadata(locale: Locale, pageKey: LegalPageKey): Promise<Metadata> {
  const messages = (await getMessages({ locale })) as Messages;
  const page = messages.legal[pageKey];
  const pathname = LEGAL_PATHS[pageKey];
  const siteName = getSiteName(messages);
  return {
    title: page.title,
    description: page.description,
    alternates: { canonical: localizeHref(pathname, locale), languages: languageAlternates(pathname) },
    openGraph: buildOpenGraph({ locale, title: page.title, description: page.description, url: localizedSiteUrl(pathname, locale), siteName }),
    twitter: buildTwitter({ title: page.title, description: page.description }),
  };
}

export async function LegalPage({ locale, pageKey }: { locale: Locale; pageKey: LegalPageKey }) {
  const messages = (await getMessages({ locale })) as Messages;
  const page = messages.legal[pageKey];
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
      <article className="rounded-3xl border border-border bg-card/70 p-6 sm:p-8">
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground">{page.title}</h1>
        <div className="mt-8 space-y-5 leading-8 text-muted-foreground">
          {page.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        </div>
      </article>
    </main>
  );
}
