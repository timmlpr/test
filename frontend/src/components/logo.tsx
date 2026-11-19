"use client";
import { useId } from "react";
import { brand } from "@/lib/brand";

/** Original mark: a footprint whose toes dissolve into dots – "leaving only a low trace". */
export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  const gid = `fpg${useId().replace(/:/g, "")}`; // unique per instance: hidden copies must not own the gradient
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#2563eb" />
          <stop offset="1" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#${gid})`} />
      <path d="M27 54c-6 0-9-5-8.5-11 .4-5 3-8.5 3.6-13 .5-4 4-6.5 8-6 4.6.6 6.4 4.5 5.9 9-.6 5.2-3.3 7.6-3.1 12 .2 5-1.7 9-5.9 9Z" fill="#fff" />
      <circle cx="40.5" cy="21" r="3.6" fill="#fff" fillOpacity=".95" />
      <circle cx="34" cy="16.5" r="3" fill="#fff" fillOpacity=".75" />
      <circle cx="27.8" cy="15.2" r="2.5" fill="#fff" fillOpacity=".55" />
      <circle cx="22.4" cy="17" r="2" fill="#fff" fillOpacity=".38" />
      <circle cx="18.5" cy="20.5" r="1.6" fill="#fff" fillOpacity=".22" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold text-lg ${className ?? ""}`}>
      <LogoMark />
      <span>{brand.name}</span>
    </span>
  );
}
