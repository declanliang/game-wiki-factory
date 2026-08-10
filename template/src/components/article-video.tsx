import { ExternalLink } from "lucide-react";

export type ArticleVideo = {
  videoId: string;
  title: string;
  url?: string;
  channelName?: string;
};

export function ArticleRelatedVideo({
  video,
  label = "Related Video",
  description = "Watch a related gameplay video, then use the guide below for the specific steps and checks.",
  watchLabel = "YouTube",
}: {
  video: ArticleVideo;
  label?: string;
  description?: string;
  watchLabel?: string;
}) {
  const url = video.url || `https://www.youtube.com/watch?v=${video.videoId}`;
  return (
    <section
      className="mt-8 overflow-hidden rounded-2xl border border-border bg-card/70"
      aria-labelledby="article-related-video"
      data-ad-exclusion="article-video"
    >
      <div className="border-b border-border px-5 py-4">
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-[hsl(var(--nav-theme))]">
          {label}
        </p>
        <h2
          id="article-related-video"
          className="mt-2 text-xl font-bold tracking-tight text-foreground"
        >
          {video.title}
        </h2>
        {video.channelName ? (
          <p className="mt-1 text-sm text-muted-foreground">
            From {video.channelName}
          </p>
        ) : null}
      </div>
      <div className="relative aspect-video bg-black">
        <iframe
          className="absolute inset-0 h-full w-full"
          src={`https://www.youtube-nocookie.com/embed/${video.videoId}?rel=0`}
          title={video.title}
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
        />
      </div>
      <div className="flex items-center justify-between gap-4 px-5 py-4">
        <p className="text-sm leading-6 text-muted-foreground">
          {description}
        </p>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-[hsl(var(--nav-theme))] hover:underline"
        >
          {watchLabel}
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>
    </section>
  );
}
