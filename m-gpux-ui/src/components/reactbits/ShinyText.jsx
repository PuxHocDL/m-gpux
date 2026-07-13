/** ShinyText — a sweeping sheen runs across the text. */
export default function ShinyText({ text, className = "" }) {
  return (
    <span className={`shine-text animate-shimmer font-semibold ${className}`}>{text}</span>
  );
}
