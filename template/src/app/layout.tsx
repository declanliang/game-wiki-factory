import "./globals.css";
import { SITE_THEME } from "@/config/theme";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-site-theme={SITE_THEME}>
      <body>{children}</body>
    </html>
  );
}
