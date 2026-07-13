/**
 * AuroraBackground — soft, slowly drifting pastel-orange light blobs. Pure CSS
 * (blur + keyframes), so it's cheap and respects the page's warm theme.
 */
export default function AuroraBackground({ className = "" }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden="true">
      <div className="absolute -top-32 -left-24 h-[28rem] w-[28rem] rounded-full bg-brand-300/40 blur-3xl animate-aurora" />
      <div
        className="absolute top-10 right-[-6rem] h-[26rem] w-[26rem] rounded-full bg-brand-400/30 blur-3xl animate-aurora"
        style={{ animationDelay: "-5s" }}
      />
      <div
        className="absolute bottom-[-8rem] left-1/3 h-[24rem] w-[24rem] rounded-full bg-amber-200/40 blur-3xl animate-aurora"
        style={{ animationDelay: "-9s" }}
      />
    </div>
  );
}
