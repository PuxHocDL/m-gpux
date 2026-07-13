/** Marquee — an infinite horizontal scroller; duplicates its items for a seamless loop. */
export default function Marquee({ items = [], className = "", renderItem }) {
  const row = [...items, ...items];
  return (
    <div className={`mask-fade-x overflow-hidden ${className}`}>
      <div className="flex w-max animate-marquee gap-3">
        {row.map((it, i) => (
          <div key={i} className="shrink-0">
            {renderItem ? renderItem(it, i) : <span>{it}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
