// Runtime availability for Cloudflare Pages. Static site builds cannot see
// environment variables added later in the Pages dashboard, so clients probe
// this endpoint before mounting any iframe or reserving ad space.

type Env = Record<string, string | undefined>;

const ENV_KEYS = {
  nativeBanner: "AD_NATIVE_BANNER_B64",
  nativeBannerMobile: "AD_NATIVE_BANNER_MOBILE_B64",
  banner728x90: "AD_BANNER_728X90_B64",
  banner300x250: "AD_BANNER_300X250_B64",
  banner468x60: "AD_BANNER_468X60_B64",
  sidebar160x600: "AD_SIDEBAR_160X600_B64",
  sidebar160x300: "AD_SIDEBAR_160X300_B64",
  mobile320x50: "AD_MOBILE_320X50_B64",
} as const;

function hasValidBase64(value: string | undefined): boolean {
  if (!value?.trim()) return false;
  try {
    return Boolean(atob(value.trim()).trim());
  } catch {
    return false;
  }
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const availability = Object.fromEntries(
    Object.entries(ENV_KEYS).map(([format, key]) => [
      format,
      hasValidBase64(context.env[key]),
    ]),
  );
  return Response.json(availability, {
    headers: {
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
};
