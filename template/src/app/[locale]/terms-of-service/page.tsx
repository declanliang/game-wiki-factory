import { buildLegalMetadata, LegalPage } from "@/components/legal-page";
import type { Locale } from "@/i18n/routing";

export async function generateMetadata({ params }: { params: Promise<{ locale: Locale }> }) {
  return buildLegalMetadata((await params).locale, "termsOfService");
}

export default async function TermsOfServicePage({ params }: { params: Promise<{ locale: Locale }> }) {
  return <LegalPage locale={(await params).locale} pageKey="termsOfService" />;
}
