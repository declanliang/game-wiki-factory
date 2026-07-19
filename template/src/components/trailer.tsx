// Trailer video modal — needs client-side interactivity (onClick, direct DOM access for the
// <dialog> element), so it's kept in its own "use client" file, separate from site.tsx (which
// touches Node's `fs` via getDynamicNavigation and must never be imported by a client component).
"use client";

import Image from "next/image";
import { Play } from "lucide-react";

export function TrailerCard({ videoId, gameName }: { videoId: string; gameName?: string }) {
  return (
    <div className="group relative cursor-pointer overflow-hidden rounded-2xl border border-border shadow-lg transition-all duration-200">
      <div className="relative aspect-video w-full">
        <Image src="/images/hero-trailer-thumbnail.jpg" alt={gameName ? `${gameName} Official Trailer` : "Official Trailer"} fill sizes="(min-width: 640px) 640px, 100vw" priority className="object-cover transition-all duration-200 group-hover:brightness-80" />
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex size-20 items-center justify-center rounded-full bg-primary/10 backdrop-blur-md transition-transform duration-200 group-hover:scale-105 sm:size-24">
          <div className="flex size-14 items-center justify-center rounded-full bg-gradient-to-b from-primary/30 to-primary shadow-md transition-transform duration-200 group-hover:scale-110 sm:size-16">
            <Play className="size-6 fill-white text-white sm:size-7" style={{ filter: "drop-shadow(rgba(0,0,0,0.07) 0 4px 3px) drop-shadow(rgba(0,0,0,0.06) 0 2px 2px)" }} />
          </div>
        </div>
      </div>
      <span className="absolute bottom-2.5 right-2.5 rounded-md bg-black/70 px-2 py-0.5 text-[11px] text-white">YouTube</span>
    </div>
  );
}

export function TrailerDialog({ videoId }: { videoId: string }) {
  return (
    <dialog id="trailer-dialog" className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm opacity-0 pointer-events-none transition-opacity duration-200" onClick={(e) => { const d = document.getElementById("trailer-dialog") as HTMLDialogElement; if (e.target === d) { d.close(); d.classList.add("opacity-0", "pointer-events-none"); d.classList.remove("opacity-100", "pointer-events-auto"); } }}>
      <div className="relative w-full max-w-4xl mx-4">
        <iframe id="trailer-iframe" className="aspect-video w-full rounded-xl" allow="autoplay; encrypted-media" allowFullScreen />
        <button className="absolute -top-10 right-0 text-white/80 hover:text-white text-sm font-medium" onClick={() => { const d = document.getElementById("trailer-dialog") as HTMLDialogElement; d.close(); d.classList.add("opacity-0", "pointer-events-none"); d.classList.remove("opacity-100", "pointer-events-auto"); }}>✕ Close</button>
      </div>
    </dialog>
  );
}

export function TrailerButton({ videoId, gameName }: { videoId: string; gameName?: string }) {
  return (
    <>
      <button type="button" className="w-full" aria-haspopup="dialog" onClick={() => { const d = document.getElementById("trailer-dialog") as HTMLDialogElement; const f = document.getElementById("trailer-iframe") as HTMLIFrameElement; f.src = `https://www.youtube.com/embed/${videoId}?autoplay=1`; d.showModal(); d.classList.remove("opacity-0", "pointer-events-none"); d.classList.add("opacity-100", "pointer-events-auto"); }}>
        <TrailerCard videoId={videoId} gameName={gameName} />
      </button>
      <TrailerDialog videoId={videoId} />
    </>
  );
}
