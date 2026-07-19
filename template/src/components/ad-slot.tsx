"use client";

import { useEffect, useRef } from "react";

/**
 * One env var per ad format. Each value should hold the ad network's raw
 * embed snippet (whatever you copy-paste from AdSense / PropellerAds /
 * Adsterra / etc — including any <script> tags). Leave unset and the slot
 * renders nothing, so it's safe to wire up before you have a network to
 * plug in.
 */
const AD_SNIPPETS = {
  socialBar: process.env.NEXT_PUBLIC_AD_SOCIAL_BAR,
  nativeBanner: process.env.NEXT_PUBLIC_AD_NATIVE_BANNER,
  banner728x90: process.env.NEXT_PUBLIC_AD_BANNER_728X90,
  banner300x250: process.env.NEXT_PUBLIC_AD_BANNER_300X250,
  banner468x60: process.env.NEXT_PUBLIC_AD_BANNER_468X60,
  sidebar160x600: process.env.NEXT_PUBLIC_AD_SIDEBAR_160X600,
  sidebar160x300: process.env.NEXT_PUBLIC_AD_SIDEBAR_160X300,
  mobile320x50: process.env.NEXT_PUBLIC_AD_MOBILE_320X50,
} as const;

export type AdFormat = keyof typeof AD_SNIPPETS;

const AD_SIZES: Record<AdFormat, { width?: number; height: number }> = {
  socialBar: { height: 50 },
  nativeBanner: { height: 100 },
  banner728x90: { width: 728, height: 90 },
  banner300x250: { width: 300, height: 250 },
  banner468x60: { width: 468, height: 60 },
  sidebar160x600: { width: 160, height: 600 },
  sidebar160x300: { width: 160, height: 300 },
  mobile320x50: { width: 320, height: 50 },
};

/**
 * innerHTML never executes embedded <script> tags, so ad network snippets
 * (which are almost always script-driven) silently no-op if you just
 * dangerouslySetInnerHTML them. Re-creating each <script> tag forces the
 * browser to actually run it.
 */
function injectAdHtml(container: HTMLElement, html: string) {
  container.innerHTML = html;
  const scripts = Array.from(container.querySelectorAll("script"));
  for (const oldScript of scripts) {
    const newScript = document.createElement("script");
    for (const attr of Array.from(oldScript.attributes)) newScript.setAttribute(attr.name, attr.value);
    newScript.textContent = oldScript.textContent;
    oldScript.replaceWith(newScript);
  }
}

export function AdSlot({ format, className }: { format: AdFormat; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const snippet = AD_SNIPPETS[format];
  const size = AD_SIZES[format];

  useEffect(() => {
    if (ref.current && snippet) injectAdHtml(ref.current, snippet);
  }, [snippet]);

  if (!snippet) return null;

  return (
    <div
      ref={ref}
      className={className}
      style={{ width: size.width, minHeight: size.height, margin: "0 auto" }}
      data-ad-format={format}
    />
  );
}
