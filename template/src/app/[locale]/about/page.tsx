import { LegalPage } from "@/components/legal-page";

export default function AboutPage() {
  return (
    <LegalPage title="About">
      <p>{"__GAME_NAME__"} Wiki is an independent fan-built guide hub covering everything about {"__GAME_NAME__"}, for new and veteran players alike.</p>
      <p>The layout, navigation, article cards, and detail format are built from a reusable game wiki template.</p>
    </LegalPage>
  );
}
