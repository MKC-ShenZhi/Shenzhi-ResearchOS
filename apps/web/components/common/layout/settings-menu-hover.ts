type Point = { x: number; y: number };
type MenuRect = { left: number; right: number; top: number; bottom: number };

const TOP_OVERSHOOT_DISTANCE = 48;
const TOP_OVERSHOOT_SIDE_PADDING = 16;
const TOP_OVERSHOOT_TIMEOUT = 800;

export type HoverIntent = {
  origin: Point;
  point: Point;
  furthestX: number;
  startedAt: number;
  progressedAt: number;
  overshotAt: number | null;
};

export function startHoverIntent(point: Point, now: number): HoverIntent {
  return { origin: point, point, furthestX: point.x, startedAt: now, progressedAt: now, overshotAt: null };
}

/** A narrow origin widens to the real menu's left edge; it never intercepts DOM events. */
export function advanceHoverIntent(intent: HoverIntent, point: Point, menu: MenuRect, now: number): HoverIntent | null {
  if (now - intent.startedAt >= 5000) return null;
  if (intent.overshotAt !== null && now - intent.overshotAt >= TOP_OVERSHOOT_TIMEOUT) return null;
  // Permit a small overshoot above Profile, including a downward correction.
  // The deadline starts on first entry and cannot be renewed by pointer jitter.
  if (point.x >= menu.left - TOP_OVERSHOOT_SIDE_PADDING && point.x <= menu.right + TOP_OVERSHOOT_SIDE_PADDING &&
    point.y >= menu.top - TOP_OVERSHOOT_DISTANCE && point.y < menu.top) {
    return { ...intent, point, overshotAt: intent.overshotAt ?? now };
  }
  const padding = 8;
  const startX = intent.origin.x - padding;
  const endX = menu.left;
  if (endX <= startX || point.x < startX || point.x > endX + padding) return null;
  const fraction = Math.min(1, (point.x - startX) / (endX - startX));
  const top = (intent.origin.y - padding) * (1 - fraction) + (menu.top - TOP_OVERSHOOT_DISTANCE) * fraction;
  const bottom = intent.origin.y + padding + (menu.bottom - intent.origin.y) * fraction;
  if (point.y < top || point.y > bottom || point.x < intent.furthestX - padding) return null;
  // Slow continuous progress is protected beyond the initial 300ms, but pauses and
  // a hard deadline prevent an abandoned corridor from keeping the menu open.
  if (now - intent.progressedAt >= 750) return null;
  const progressed = point.x > intent.furthestX + 1;
  return {
    ...intent,
    point,
    furthestX: progressed ? point.x : intent.furthestX,
    progressedAt: progressed ? now : intent.progressedAt,
  };
}
