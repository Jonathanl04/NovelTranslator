import { BookOpen, ClipboardList, Library, Moon, Settings, Sun, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type AppPage = "library" | "workspace" | "glossary" | "settings";

export function AppHeader({ page, status, error, darkMode, onNavigate, onToggleTheme }: {
  page: AppPage;
  status: string;
  error: boolean;
  darkMode: boolean;
  onNavigate: (page: AppPage) => void;
  onToggleTheme: () => void;
}) {
  const items = [
    { page: "library" as const, label: "Books", icon: Library },
    { page: "workspace" as const, label: "Translate", icon: WandSparkles },
    { page: "glossary" as const, label: "Glossary", icon: ClipboardList },
    { page: "settings" as const, label: "Settings", icon: Settings },
  ];
  return (
    <header className="sticky top-0 z-20 grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b bg-background/95 px-5 pr-16 backdrop-blur max-[760px]:h-auto max-[760px]:grid-cols-1 max-[760px]:gap-3 max-[760px]:px-3 max-[760px]:py-3">
      <div className="flex items-center gap-2 max-[760px]:pr-14">
        <BookOpen className="size-5 text-teal-700" />
        <h1 className="text-base font-semibold">Novel Translator</h1>
      </div>
      <nav className="flex w-full min-w-0 items-center justify-center gap-1 rounded-lg bg-muted p-1">
        {items.map((item) => {
          const Icon = item.icon;
          return <Button key={item.page} type="button" size="sm" variant={page === item.page ? "secondary" : "ghost"}
            className={cn("relative", page === item.page && "after:absolute after:inset-x-2 after:-bottom-1 after:h-0.5 after:rounded-full after:bg-primary")}
            onClick={() => onNavigate(item.page)}><Icon />{item.label}</Button>;
        })}
      </nav>
      <div className={cn("min-w-0 truncate text-right text-sm text-muted-foreground max-[760px]:pr-14 max-[760px]:text-left", error && "text-destructive")}>{status || "Ready"}</div>
      <Button type="button" variant="outline" size="icon" className="absolute right-5 top-3 max-[760px]:right-3 max-[760px]:top-3"
        onClick={onToggleTheme} aria-label={darkMode ? "Use light mode" : "Use dark mode"} title={darkMode ? "Light mode" : "Dark mode"}>
        {darkMode ? <Sun /> : <Moon />}
      </Button>
    </header>
  );
}
