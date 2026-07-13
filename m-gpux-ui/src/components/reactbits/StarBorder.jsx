/**
 * StarBorder — a conic pastel-orange light sweeps around the border of a pill
 * button. Renders as <a> or <button>.
 */
export default function StarBorder({ as: Tag = "button", children, className = "", ...rest }) {
  return (
    <Tag
      className={`group relative inline-flex items-center justify-center overflow-hidden rounded-xl p-[1.5px] ${className}`}
      {...rest}
    >
      <span
        className="absolute inset-[-200%] animate-[spin_4s_linear_infinite]"
        style={{
          background:
            "conic-gradient(from 0deg, transparent 0deg, #FB923C 60deg, #FDBA74 120deg, transparent 180deg, transparent 360deg)",
        }}
      />
      <span className="relative inline-flex items-center gap-2 rounded-[10px] bg-white px-5 py-3 text-sm font-semibold text-brand-700 transition-colors group-hover:bg-brand-50">
        {children}
      </span>
    </Tag>
  );
}
