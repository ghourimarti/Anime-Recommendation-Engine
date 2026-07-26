"use client";

import { Command } from "cmdk";
import { History, Home, Search, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EXAMPLE_PROMPTS } from "@/lib/examples";

// Self-contained: renders the header trigger button AND the modal, sharing one
// local open state. ⌘K / Ctrl+K toggles; Esc closes. Example prompts navigate to
// /?q=… which the hero reads to prefill — so the palette stays decoupled from
// the query component's state, and prompts become shareable URLs for free.
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function go(path: string) {
    setOpen(false);
    router.push(path);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-md border border-border/70 bg-secondary/50 px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-border hover:text-foreground"
        aria-label="Open command palette"
      >
        <Search className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Search…</span>
        <kbd className="hidden rounded border border-border bg-background px-1.5 font-mono text-[10px] sm:inline">
          ⌘K
        </kbd>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/70 px-4 pt-[18vh] backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <Command
            label="Command menu"
            className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-border px-4">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Command.Input
                autoFocus
                placeholder="Search or jump to…"
                className="flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
            <Command.List className="max-h-80 overflow-y-auto p-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground">
              <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
                No results.
              </Command.Empty>

              <Command.Group heading="Navigation">
                <PaletteItem onSelect={() => go("/")} icon={<Home className="h-4 w-4" />}>
                  New search
                </PaletteItem>
                <PaletteItem
                  onSelect={() => go("/history")}
                  icon={<History className="h-4 w-4" />}
                >
                  Watchlist
                </PaletteItem>
              </Command.Group>

              <Command.Group heading="Try a prompt">
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <PaletteItem
                    key={prompt}
                    onSelect={() => go(`/?q=${encodeURIComponent(prompt)}`)}
                    icon={<Sparkles className="h-4 w-4 text-primary" />}
                  >
                    {prompt}
                  </PaletteItem>
                ))}
              </Command.Group>
            </Command.List>
          </Command>
        </div>
      )}
    </>
  );
}

function PaletteItem({
  children,
  icon,
  onSelect,
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-sm text-foreground aria-selected:bg-secondary aria-selected:text-foreground"
    >
      {icon}
      <span className="truncate">{children}</span>
    </Command.Item>
  );
}
