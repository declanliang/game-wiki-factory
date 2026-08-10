"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { AD_SIZES, type AdAvailability, type AdFormat } from "@/lib/ad-types";

const AdContext = createContext<AdAvailability | null>(null);
const AD_RENDER_ROUTE = "/api/ads/render";

export function AdProvider({ availability, children }: { availability: AdAvailability; children: React.ReactNode }) {
  const [runtimeAvailability, setRuntimeAvailability] = useState(availability);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/ads/availability", { cache: "no-store", signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((value) => {
        if (value && typeof value === "object") {
          setRuntimeAvailability(value as AdAvailability);
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  return <AdContext.Provider value={runtimeAvailability}>{children}</AdContext.Provider>;
}

export function useAdEnabled(format: AdFormat) {
  return Boolean(useContext(AdContext)?.[format]);
}

export function AdSlot({ format, className = "", eager = false }: { format: AdFormat; className?: string; eager?: boolean }) {
  const enabled = useAdEnabled(format);
  if (!enabled) return null;
  const isNative = format === "nativeBanner" || format === "nativeBannerMobile";
  const size = isNative ? null : AD_SIZES[format];
  const boxStyle = size
    ? ({
        "--ad-width": `${size.width}px`,
        "--ad-height": `${size.height}px`,
      } as React.CSSProperties)
    : undefined;
  return (
    <div className={`relative mx-auto ${isNative ? "w-full max-w-5xl" : "h-[var(--ad-height)] w-[var(--ad-width)] max-w-full"} ${className}`} style={boxStyle} data-ad-format={format}>
      <span className="sr-only">Advertisement</span>
      <iframe
        src={`${AD_RENDER_ROUTE}/${format}`}
        title="Advertisement"
        aria-label="Advertisement"
        width={size?.width ?? "100%"}
        height={size?.height ?? "100%"}
        loading={eager ? "eager" : "lazy"}
        scrolling="no"
        referrerPolicy="strict-origin-when-cross-origin"
        className={`block border-0 ${isNative ? "absolute inset-0 h-full w-full" : ""}`}
      />
    </div>
  );
}
