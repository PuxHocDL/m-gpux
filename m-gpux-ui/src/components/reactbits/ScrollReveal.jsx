import { motion } from "framer-motion";

/** ScrollReveal — fades & lifts its children into place on scroll. */
export default function ScrollReveal({
  children,
  className = "",
  delay = 0,
  y = 28,
  once = true,
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, margin: "-10% 0px" }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
