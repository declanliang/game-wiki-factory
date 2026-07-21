import {
  BookOpen,
  Bot,
  Boxes,
  CircleDollarSign,
  Crosshair,
  Layers3,
  Map,
  Newspaper,
  Gamepad2,
  ScrollText,
  Settings2,
  ShieldAlert,
  Sparkles,
  Swords,
  Tag,
  Trophy,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import sitePlan from "./site-plan.json";

export type SitePlanCategory = {
  id: string;
  order: number;
  labels: Record<string, string>;
  description: string;
  status: "planned" | "published" | "unfulfilled";
  articleCount: number;
};

const ICONS: Record<string, LucideIcon> = {
  guide: BookOpen,
  progression: TrendingUp,
  mechanics: Settings2,
  updates: Newspaper,
  "tier-list": Trophy,
  enemies: ShieldAlert,
  floors: Layers3,
  upgrades: Sparkles,
  economy: CircleDollarSign,
  bosses: Swords,
  weapons: Crosshair,
  characters: Bot,
  codes: Tag,
  maps: Map,
  items: Boxes,
  modes: Gamepad2,
  quests: ScrollText,
};

export const SITE_PLAN_CATEGORIES = (sitePlan.categories as SitePlanCategory[])
  .filter((category) => category.status === "published")
  .sort((a, b) => a.order - b.order);

export const NAVIGATION_CONFIG: {
  key: string;
  path: string;
  icon: LucideIcon;
  isContentType: boolean;
}[] = SITE_PLAN_CATEGORIES.map((category) => ({
  key: category.id,
  path: `/${category.id}`,
  icon: ICONS[category.id] ?? Tag,
  isContentType: true,
}));

export const CONTENT_TYPES = SITE_PLAN_CATEGORIES.map((category) => category.id);
