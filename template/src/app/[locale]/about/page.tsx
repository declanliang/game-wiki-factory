import { buildLegalMetadata, LegalPage } from "@/components/legal-page";
import type { Locale } from "@/i18n/routing";

export async function generateMetadata({ params }: { params: Promise<{ locale: Locale }> }) {
  return buildLegalMetadata((await params).locale, "about");
}

export default async function AboutPage({ params }: { params: Promise<{ locale: Locale }> }) {
  return <LegalPage locale={(await params).locale} pageKey="about" />;
}
