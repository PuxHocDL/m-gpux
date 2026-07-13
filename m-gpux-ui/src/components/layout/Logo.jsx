/** Brand mark: a pastel-orange lightning tile + wordmark. */
export default function Logo({ className = "", showText = true }) {
  return (
    <a href="#top" className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-grad shadow-soft">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
          <path
            d="M13 2 L5 13 h6 l-2 9 8-12 h-6 z"
            fill="#FFF7ED"
            stroke="#FFFFFF"
            strokeWidth="1"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {showText && (
        <span className="font-display text-lg font-extrabold tracking-tight text-ink">
          m-gpux
        </span>
      )}
    </a>
  );
}
