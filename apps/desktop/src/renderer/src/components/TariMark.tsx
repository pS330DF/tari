/** TARI's original mark: an attentive "lens" — a rounded diamond with an aperture slit. */
export function TariMark({ size = 18, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 2.8 21.2 12 12 21.2 2.8 12Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" className="text-accent" />
      <path d="M7.2 12h9.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-fg-muted" />
      <circle cx="12" cy="12" r="2.1" className={active ? "fill-accent-strong" : "fill-fg-muted"} />
    </svg>
  );
}
