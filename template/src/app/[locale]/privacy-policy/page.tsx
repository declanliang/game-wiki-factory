import { LegalPage } from "@/components/legal-page";

export default function PrivacyPolicyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>This fan wiki provides informational game guides for {"__GAME_NAME__"}. We do not request account credentials, game passwords, or private payment information.</p>
      <p>Basic analytics, advertising, and hosting providers may process standard technical information such as device type, browser, approximate region, and visited pages.</p>
      <p>External links may lead to the official game site, Discord, YouTube, or community tools. Those services are governed by their own privacy policies.</p>
    </LegalPage>
  );
}
