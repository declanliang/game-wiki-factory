import { LegalPage } from "@/components/legal-page";

export default function CopyrightPage() {
  return (
    <LegalPage title="Copyright">
      <p>{"__GAME_NAME__"} and related media belong to their respective owners.</p>
      <p>This site is a non-official fan wiki implementation for educational and guide presentation purposes.</p>
      <p>If you own rights to content displayed here and have a concern, please contact the site operator for review.</p>
    </LegalPage>
  );
}
