/** Brand mark shared by navigation, footer and product mockups. */
export default function Logo({ className = "", showText = true, inverse = false }) {
  return (
    <a href="/" className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="grid h-9 w-9 place-items-center rounded-full border border-brand-700 bg-brand-700 shadow-soft">
        <svg viewBox="0 0 64 64" className="h-7 w-7" fill="none" aria-hidden="true">
          <g stroke="#FBFAF6" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 22c0-9 6-14 14-14 9 0 14 6 14 15v18c0 10-7 15-28 16V22Z" />
            <path d="M18 22c0 12 6 18 15 18 8 0 13-6 13-18" />
            <path d="M15 14c0 6 5 2 10 4 5 2 7 6 7 12M49 14c0 6-5 2-10 4-5 2-7 6-7 12" />
            <path d="M23 41c2 7 0 12-4 14" />
          </g>
          <circle cx="25" cy="25" r="4" fill="#FBFAF6" />
          <circle cx="39" cy="25" r="4" fill="#FBFAF6" />
          <circle cx="25" cy="25" r="1.5" fill="#00664F" />
          <circle cx="39" cy="25" r="1.5" fill="#00664F" />
        </svg>
      </span>
      {showText && (
        <span className={`font-sans text-lg font-bold tracking-[-0.04em] ${inverse ? "text-white" : "text-ink"}`}>
          m-gpux<span className="text-brand-500">.</span>
        </span>
      )}
    </a>
  );
}
