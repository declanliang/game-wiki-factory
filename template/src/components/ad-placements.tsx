"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { AdSlot, useAdEnabled } from "@/components/ad-slot";

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

function useResolvedMediaQuery(query: string) {
  const [matches, setMatches] = useState<boolean | null>(null);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

export function TopStickyAd() {
  const [dismissed, setDismissed] = useState(false);
  const enabled = useAdEnabled("mobile320x50");
  if (!enabled || dismissed) return null;
  return <><style>{`:root{--top-ad-height:50px}`}</style><div className="h-[50px]" aria-hidden="true" /><div className="pointer-events-none fixed inset-x-0 top-0 z-[60] flex h-[50px] items-center justify-center bg-background" data-top-ad-visible><div className="pointer-events-auto relative h-[50px] w-[320px] max-w-full"><AdSlot format="mobile320x50" eager /><button type="button" aria-label="Close advertisement" onClick={() => setDismissed(true)} className="absolute right-1 top-1 z-10 grid h-6 w-6 place-items-center rounded-full border border-white/25 bg-black/80 text-white shadow-md transition hover:bg-black"><X className="h-3.5 w-3.5" /></button></div></div></>;
}

export function NativeFlowAd({ className = "" }: { className?: string }) {
  const desktop = useResolvedMediaQuery("(min-width: 900px)");
  const desktopEnabled = useAdEnabled("nativeBanner");
  const mobileEnabled = useAdEnabled("nativeBannerMobile");
  if (desktop === null) return null;
  if (desktop) {
    return desktopEnabled ? <AdSlot format="nativeBanner" className={`aspect-[4/1] min-h-[80px] ${className}`} /> : null;
  }
  return mobileEnabled ? <AdSlot format="nativeBannerMobile" className={`aspect-square w-full max-w-[300px] ${className}`} /> : null;
}

export function ResponsiveContentAd({ className = "" }: { className?: string }) {
  const desktop = useMediaQuery("(min-width: 900px)");
  const banner728 = useAdEnabled("banner728x90");
  const banner300 = useAdEnabled("banner300x250");
  if (desktop && banner728) return <AdSlot format="banner728x90" className={className} />;
  return banner300 ? <AdSlot format="banner300x250" className={className} /> : null;
}

export function GlobalFooterAds() {
  const desktop = useResolvedMediaQuery("(min-width: 900px)");
  const banner728 = useAdEnabled("banner728x90");
  const banner468 = useAdEnabled("banner468x60");
  const banner300 = useAdEnabled("banner300x250");
  if (desktop === null) return null;
  const format = desktop
    ? banner728
      ? "banner728x90"
      : banner468
        ? "banner468x60"
        : null
    : banner300
      ? "banner300x250"
      : null;
  if (!format) return null;
  return <section className="mx-auto mt-20 w-full max-w-5xl border-t border-border/70 px-4 py-10 sm:px-6" aria-label="Footer advertisement"><AdSlot format={format} /></section>;
}

export function DesktopBanner728({ className = "" }: { className?: string }) {
  const desktop = useMediaQuery("(min-width: 900px)");
  const enabled = useAdEnabled("banner728x90");
  return desktop && enabled ? <AdSlot format="banner728x90" className={className} /> : null;
}

export function DesktopArticleRailAds() {
  const wide = useMediaQuery("(min-width: 1280px)");
  const tall = useMediaQuery("(min-height: 720px)");
  const tallEnabled = useAdEnabled("sidebar160x600");
  const compactEnabled = useAdEnabled("sidebar160x300");
  if (!wide) return null;
  const format = tall && tallEnabled
    ? "sidebar160x600"
    : compactEnabled
      ? "sidebar160x300"
      : null;
  if (!format) return null;
  return <aside className="sticky top-[calc(var(--top-ad-height,0px)+5.5rem)] hidden self-start 2xl:block" aria-label="Left advertisement"><AdSlot format={format} eager /></aside>;
}

export function ArticleInlineAd({ containerId }: { containerId: string }) {
  const enabled = useAdEnabled("banner300x250");
  const [mounts, setMounts] = useState<HTMLElement[]>([]);
  useEffect(() => {
    if (!enabled) { setMounts([]); return; }
    const container = document.getElementById(containerId);
    if (!container) return;
    const paragraphs = Array.from(container.children).filter(
      (node): node is HTMLParagraphElement =>
        node instanceof HTMLParagraphElement &&
        !node.closest("[data-ad-exclusion]") &&
        !node.matches(".not-prose *"),
    );
    const maxAds = paragraphs.length >= 23 ? 3 : paragraphs.length >= 14 ? 2 : paragraphs.length >= 8 ? 1 : 0;
    const lastAllowedIndex = Math.min(
      Math.floor(paragraphs.length * 0.75) - 1,
      paragraphs.length - 5,
    );
    const targetIndexes = [2, 9, 16]
      .filter((index) => index <= lastAllowedIndex)
      .slice(0, maxAds);
    const nodes = targetIndexes.map((index) => { const node = document.createElement("div"); node.className = "not-prose my-12 flex justify-center"; node.dataset.articleInlineAd = "true"; paragraphs[index].insertAdjacentElement("afterend", node); return node; });
    setMounts(nodes);
    return () => nodes.forEach((node) => node.remove());
  }, [containerId, enabled]);
  if (!enabled) return null;
  return <>{mounts.map((mount, index) => createPortal(<AdSlot format="banner300x250" />, mount, `article-ad-${index}`))}</>;
}
