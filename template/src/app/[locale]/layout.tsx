import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { hasLocale } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { NextIntlClientProvider } from "next-intl";
import { notFound } from "next/navigation";
import { ThemeProvider } from "next-themes";
import { SiteFooter, SiteHeader } from "@/components/site";
import { JsonLd } from "@/components/site-widgets";
import { AdProvider } from "@/components/ad-slot";
import { GlobalFooterAds, TopStickyAd } from "@/components/ad-placements";
import { Analytics } from "@/components/analytics";
import { getSiteName, localizedSiteUrl, SITE_URL } from "@/config/site";
import { routing } from "@/i18n/routing";
import { buildOpenGraph, buildSiteGraph, buildTwitter, shouldIndex } from "@/lib/seo";
import { getAdAvailability } from "@/lib/ad-config";
import en from "@/locales/en.json";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

type Messages = typeof en;

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const messages = (await getMessages({ locale })) as Messages;
  const siteName = getSiteName(messages);
  const description = messages.site.description;
  const pageUrl = localizedSiteUrl("/", locale);
  return {
    metadataBase: new URL(SITE_URL),
    title: { default: siteName, template: "%s" },
    description,
    manifest: "/manifest.json",
    icons: {
      icon: [
        { url: "/favicon.ico" },
        { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
        { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      ],
      apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    },
    robots: shouldIndex() ? undefined : { index: false, follow: false },
    openGraph: buildOpenGraph({ locale, title: siteName, description, url: pageUrl, siteName }),
    twitter: buildTwitter({ title: siteName, description }),
  };
}

export default async function LocaleLayout({ children, params }: { children: React.ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const messages = (await getMessages()) as Messages;
  const siteGraph = buildSiteGraph(messages, locale);
  const adAvailability = getAdAvailability();

  return (
    <html lang={locale} className={`${inter.variable}`} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <NextIntlClientProvider messages={messages}>
            <AdProvider availability={adAvailability}>
              <JsonLd data={siteGraph} />
              <TopStickyAd />
              <SiteHeader locale={locale} />
              {children}
              <GlobalFooterAds />
              <SiteFooter locale={locale} />
              <Analytics />
            </AdProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
