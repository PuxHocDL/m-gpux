/** GradientText — an animated pastel-orange gradient flows through the text. */
export default function GradientText({ children, className = "" }) {
  return (
    <span
      className={`bg-clip-text text-transparent animate-gradient-x ${className}`}
      style={{
        backgroundImage:
          "linear-gradient(90deg,#EA580C,#FB923C,#FDBA74,#FB923C,#EA580C)",
        backgroundSize: "200% 100%",
      }}
    >
      {children}
    </span>
  );
}
