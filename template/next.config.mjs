import createNextIntlPlugin from "next-intl/plugin";
import createMDX from "@next/mdx";
import remarkGfm from "remark-gfm";

const configuredSiteUrl = process.env.NEXT_PUBLIC_SITE_URL?.trim();
if (process.env.CF_PAGES === "1") {
  if (!configuredSiteUrl) {
    throw new Error("NEXT_PUBLIC_SITE_URL is required for Cloudflare Pages builds");
  }
  const normalizedSiteUrl = /^https?:\/\//i.test(configuredSiteUrl)
    ? configuredSiteUrl
    : `https://${configuredSiteUrl}`;
  const hostname = new URL(normalizedSiteUrl).hostname.toLowerCase();
  if (hostname === "example.com" || hostname.endsWith(".example.com")) {
    throw new Error("NEXT_PUBLIC_SITE_URL must use the real Cloudflare Pages or custom domain");
  }
}

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const withMDX = createMDX({
  options: {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [],
  },
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Default Cloudflare Pages output: static export, no Node server functions.
  // Security headers moved to public/_headers; redirects/middleware removed
  // since generateStaticParams already resolves all locale routes at build time.
  output: "export",
  poweredByHeader: false,
  pageExtensions: ["ts", "tsx", "js", "jsx", "md", "mdx"],
  images: {
    unoptimized: true,
  },
};

export default withNextIntl(withMDX(nextConfig));
