"use client";
import { useId } from "react";
import { brand } from "@/lib/brand";

/** Original mark: a "T" whose stem dissolves into dots – the trace gets lower. */
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
      {/* T monogram whose stem dissolves into ever smaller dots: a trace that gets lower */}
      <rect x="15" y="14" width="34" height="9" rx="4.5" fill="#fff" />
      <rect x="27.5" y="18" width="9" height="15" rx="4.5" fill="#fff" />
      <circle cx="32" cy="39.5" r="4" fill="#fff" fillOpacity=".8" />
      <circle cx="32" cy="47" r="3" fill="#fff" fillOpacity=".55" />
      <circle cx="32" cy="53" r="2" fill="#fff" fillOpacity=".32" />
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
