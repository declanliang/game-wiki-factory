"use client";

import { createContext, useContext } from "react";
import { AD_SIZES, type AdAvailability, type AdFormat } from "@/lib/ad-types";

const AdContext = createContext<AdAvailability | null>(null);

export function AdProvider({ availability, children }: { availability: AdAvailability; children: React.ReactNode }) {
  return <AdContext.Provider value={availability}>{children}</AdContext.Provider>;
}

export function useAdEnabled(format: AdFormat) {
  return Boolean(useContext(AdContext)?.[format]);
}

export function AdSlot({ format, className = "", eager = false }: { format: AdFormat; className?: string; eager?: boolean }) {
  const enabled = useAdEnabled(format);
  if (!enabled) return null;
  const isNative = format === "nativeBanner";
  const size = isNative ? null : AD_SIZES[format];
  return (
    <div className={`relative mx-auto ${isNative ? "w-full max-w-5xl" : "max-w-full"} ${className}`} style={size ? { width: size.width, height: size.height } : undefined} data-ad-format={format}>
      <span className="sr-only">Advertisement</span>
      <iframe
        src={`/api/ads/${format}`}
        title="Advertisement"
        aria-label="Advertisement"
        width={size?.width ?? "100%"}
        height={size?.height ?? "100%"}
        loading={eager ? "eager" : "lazy"}
        scrolling="no"
        referrerPolicy="strict-origin-when-cross-origin"
        sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
        className={`block border-0 ${isNative ? "absolute inset-0 h-full w-full" : ""}`}
      />
    </div>
  );
}
