export const DEFAULT_SITE_URL: string;
export function resolveSiteUrl(value: string | undefined): string;
export function resolveDeploymentSiteUrl(env: Record<string, string | undefined>): string;
