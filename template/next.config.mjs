import createNextIntlPlugin from "next-intl/plugin";
import createMDX from "@next/mdx";
import remarkGfm from "remark-gfm";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const withMDX = createMDX({
  options: {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [],
  },
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloudflare Pages branch: static export, no Node server / Vercel Functions.
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
