export const AD_FORMATS = ["nativeBanner", "nativeBannerMobile", "banner728x90", "banner300x250", "banner468x60", "sidebar160x600", "sidebar160x300", "mobile320x50"] as const;

export type AdFormat = (typeof AD_FORMATS)[number];
export type AdAvailability = Record<AdFormat, boolean>;

export const AD_SIZES: Partial<Record<AdFormat, { width: number; height: number }>> = {
  banner728x90: { width: 728, height: 90 },
  banner300x250: { width: 300, height: 250 },
  banner468x60: { width: 468, height: 60 },
  sidebar160x600: { width: 160, height: 600 },
  sidebar160x300: { width: 160, height: 300 },
  mobile320x50: { width: 320, height: 50 },
};
