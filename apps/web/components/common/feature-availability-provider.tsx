"use client";

import Link from "next/link";
import * as React from "react";
import { Clock3, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  COMING_SOON_MESSAGE,
  COMING_SOON_NOTICE,
  isUnavailableFeatureHref,
} from "@/lib/feature-availability";

interface FeatureAvailabilityContextValue {
  showComingSoon: () => void;
}

const FeatureAvailabilityContext =
  React.createContext<FeatureAvailabilityContextValue | null>(null);

function ComingSoonDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const closeButtonRef = React.useRef<HTMLButtonElement>(null);

  React.useEffect(() => {
    if (!open) return;

    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="coming-soon-title"
        className="relative w-full max-w-sm rounded-3xl border border-line bg-card px-6 py-7 text-center shadow-pop"
      >
        <button
          ref={closeButtonRef}
          type="button"
          aria-label="关闭"
          onClick={onClose}
          className="absolute right-4 top-4 flex size-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-chip hover:text-ink"
        >
          <X className="size-4" />
        </button>
        <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
          <Clock3 className="size-6" strokeWidth={1.8} />
        </span>
        <h2 id="coming-soon-title" className="mt-4 text-lg font-semibold text-ink">
          {COMING_SOON_MESSAGE}
        </h2>
        <Button type="button" className="mt-6 min-w-24" onClick={onClose}>
          知道了
        </Button>
      </section>
    </div>
  );
}

export function FeatureAvailabilityProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const showComingSoon = React.useCallback(() => setDialogOpen(true), []);
  const closeComingSoon = React.useCallback(() => setDialogOpen(false), []);

  React.useEffect(() => {
    const url = new URL(window.location.href);
    if (
      url.searchParams.get(COMING_SOON_NOTICE.param) !==
      COMING_SOON_NOTICE.value
    ) {
      return;
    }

    const showHandle = window.setTimeout(showComingSoon, 0);
    url.searchParams.delete(COMING_SOON_NOTICE.param);
    window.history.replaceState(
      window.history.state,
      "",
      `${url.pathname}${url.search}${url.hash}`,
    );
    return () => window.clearTimeout(showHandle);
  }, [showComingSoon]);

  const value = React.useMemo(
    () => ({ showComingSoon }),
    [showComingSoon],
  );

  return (
    <FeatureAvailabilityContext.Provider value={value}>
      {children}
      <ComingSoonDialog open={dialogOpen} onClose={closeComingSoon} />
    </FeatureAvailabilityContext.Provider>
  );
}

export function useFeatureAvailability() {
  const context = React.useContext(FeatureAvailabilityContext);
  if (!context) {
    throw new Error(
      "useFeatureAvailability must be used inside FeatureAvailabilityProvider",
    );
  }
  return context;
}

export function FeatureNavigationLink({
  href,
  onClick,
  prefetch,
  ...props
}: Omit<React.ComponentProps<typeof Link>, "href"> & { href: string }) {
  const { showComingSoon } = useFeatureAvailability();
  const unavailable = isUnavailableFeatureHref(href);

  return (
    <Link
      {...props}
      href={href}
      prefetch={unavailable ? false : prefetch}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented || !unavailable) return;
        event.preventDefault();
        showComingSoon();
      }}
    />
  );
}
