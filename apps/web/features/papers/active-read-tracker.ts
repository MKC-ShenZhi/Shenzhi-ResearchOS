const ACTIVE_READ_SECONDS = 30;

/** Accumulates only foreground reader time across panel and tab switches. */
export class ActiveReadTracker {
  private identity: string | null = null;
  private visibleSeconds = 0;
  private reported = false;
  private lastTickAt: number | null = null;

  resetInterval(): void {
    this.lastTickAt = null;
  }

  tick(
    userId: string,
    paperId: string,
    isVisible: boolean,
    nowMilliseconds: number,
  ): number | null {
    if (!userId || !paperId || !Number.isFinite(nowMilliseconds)) {
      return null;
    }

    const identity = `${userId}\u0000${paperId}`;
    if (identity !== this.identity) {
      this.identity = identity;
      this.visibleSeconds = 0;
      this.reported = false;
      this.lastTickAt = null;
    }

    if (this.reported) return null;

    if (this.lastTickAt === null) {
      this.lastTickAt = nowMilliseconds;
      return null;
    }

    const elapsedSeconds = Math.max(0, (nowMilliseconds - this.lastTickAt) / 1000);
    this.lastTickAt = nowMilliseconds;
    if (isVisible) this.visibleSeconds += elapsedSeconds;
    if (this.visibleSeconds < ACTIVE_READ_SECONDS) return null;

    this.reported = true;
    return this.visibleSeconds;
  }
}
