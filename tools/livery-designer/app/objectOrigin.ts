export type ObjectOrigin = "user" | "evaluation" | "existing" | "unknown";

// Missing or future server values must never imply a historical origin.
export function objectOriginLabel(origin: unknown): string {
  switch (origin) {
    case "user": return "用户新增";
    case "evaluation": return "评测生成";
    case "existing": return "场景原有";
    default: return "来源未知";
  }
}
