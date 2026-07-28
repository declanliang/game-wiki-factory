"use client";

import Image from "next/image";
import { ExternalLink, Play } from "lucide-react";
import { useState } from "react";

type VideoLabels = {
  eyebrow: string;
  title: string;
  description: string;
  play: string;
  watchOnYouTube: string;
};

export function TrailerButton({
  videoId,
  gameName,
  labels,
}: { videoId: string; gameName: string; labels: VideoLabels }) {
  const [playing, setPlaying] = useState(false);
  const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;

  return (
    <section
      className="mx-auto max-w-[960px]"
      aria-labelledby="homepage-video-title"
    >
      <div className="mb-7 text-center">
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-[hsl(var(--nav-theme))]">
          {labels.eyebrow}
        </p>
        <h2
          id="homepage-video-title"
          className="mt-3 text-3xl font-bold tracking-tight text-foreground sm:text-5xl"
        >
          {labels.title}
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
          {labels.description}
        </p>
      </div>

      <div className="overflow-hidden rounded-[1.75rem] border border-border bg-card/70 shadow-2xl shadow-black/10">
        <div className="relative aspect-video w-full bg-black">
          {playing ? (
            <iframe
              className="absolute inset-0 h-full w-full"
              src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0`}
              title={`${gameName} gameplay video`}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
            />
          ) : (
            <button
              type="button"
              onClick={() => setPlaying(true)}
              className="group absolute inset-0 w-full overflow-hidden text-white"
              aria-label={`${labels.play}: ${gameName}`}
            >
              <Image
                src="/images/hero-trailer-thumbnail.jpg"
                alt={`${gameName} gameplay video thumbnail`}
                fill
                sizes="(min-width: 1024px) 960px, 100vw"
                className="object-cover transition duration-500 group-hover:scale-[1.015] group-hover:brightness-75"
              />
              <span className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/5 to-black/10" />
              <span className="absolute inset-0 grid place-items-center">
                <span className="grid h-20 w-20 place-items-center rounded-full border border-white/25 bg-black/45 shadow-2xl backdrop-blur-md transition duration-300 group-hover:scale-110 group-hover:bg-[hsl(var(--nav-theme))]">
                  <Play className="ml-1 h-8 w-8 fill-current" />
                </span>
              </span>
              <span className="absolute bottom-5 left-5 rounded-full border border-white/20 bg-black/55 px-4 py-2 text-sm font-semibold backdrop-blur-md">
                {labels.play}
              </span>
            </button>
          )}
        </div>
        <div className="flex items-center justify-between gap-4 px-5 py-4 sm:px-7">
          <p className="min-w-0 truncate text-sm font-medium text-muted-foreground">
            {gameName}
          </p>
          <a
            href={videoUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-[hsl(var(--nav-theme))] hover:underline"
          >
            {labels.watchOnYouTube}
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </section>
  );
}
