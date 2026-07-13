import { motion } from "framer-motion";

/**
 * SplitText — reveals text word-by-word (or letter-by-letter) when scrolled into
 * view. A React Bits staple, reimplemented on framer-motion.
 */
export default function SplitText({
  text = "",
  className = "",
  by = "word",
  delay = 0,
  stagger = 0.045,
  y = 22,
  as: Tag = "span",
  once = true,
}) {
  const parts = by === "letter" ? Array.from(text) : text.split(" ");
  const MotionTag = motion(Tag);

  return (
    <MotionTag
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once, margin: "-12% 0px" }}
      transition={{ staggerChildren: stagger, delayChildren: delay }}
      aria-label={text}
    >
      {parts.map((part, i) => (
        <span key={i} className="inline-block overflow-hidden align-bottom" aria-hidden="true">
          <motion.span
            className="inline-block"
            variants={{
              hidden: { y, opacity: 0 },
              show: { y: 0, opacity: 1 },
            }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
          >
            {part}
            {by === "word" && i < parts.length - 1 ? " " : ""}
          </motion.span>
        </span>
      ))}
    </MotionTag>
  );
}
