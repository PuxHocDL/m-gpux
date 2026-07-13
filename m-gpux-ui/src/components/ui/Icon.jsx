import {
  KeyRound,
  Cpu,
  Bookmark,
  Image,
  Globe,
  Sparkles,
  Container,
  Gauge,
  Activity,
  Users,
  ExternalLink,
  Square,
  Radar,
  Zap,
} from "lucide-react";

const MAP = {
  KeyRound,
  Cpu,
  Bookmark,
  Image,
  Globe,
  Sparkles,
  Container,
  Gauge,
  Activity,
  Users,
  ExternalLink,
  Square,
  Radar,
  Zap,
};

/** Icon — resolve a lucide icon by name (used by data-driven sections). */
export default function Icon({ name, ...props }) {
  const Cmp = MAP[name] || Sparkles;
  return <Cmp {...props} />;
}
