// Single source of truth: ../config/*.json (copied by scripts/sync-content.mjs).
import brandJson from "@/config/brand.json";
import plansJson from "@/config/plans.json";

export const brand = brandJson;
export const plans = plansJson;
export type Plans = typeof plansJson;
