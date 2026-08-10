export function YouTubeEmbed({ videoId, title }: { videoId: string; title?: string }) {
  return (
    <div className="my-4 aspect-video w-full overflow-hidden rounded-xl border border-border bg-black">
      <iframe
        src={`https://www.youtube-nocookie.com/embed/${videoId}?rel=0`}
        title={title || "YouTube video"}
        loading="lazy"
        referrerPolicy="strict-origin-when-cross-origin"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
        className="size-full"
      />
    </div>
  );
}
