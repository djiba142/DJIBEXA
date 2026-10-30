import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { LogOut, Search, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouterState } from "@tanstack/react-router";

import { AppSidebar } from "@/components/AppSidebar";
import { NotificationBell } from "@/components/NotificationBell";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";

import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import { brandLogo } from "@/lib/brand-assets";
import { useSettings } from "@/lib/settings";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  const { session, loading, can, isPlatformAdmin, fullName, roles, signOut } = useAuth();
  const { language, t } = useLocale();
  const settings = useSettings();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!loading && !session) navigate({ to: "/auth", replace: true });
    if (!loading && session?.user.must_change_password) {
      if (pathname !== "/change-password") {
        navigate({ to: "/change-password", replace: true });
      }
      return;
    }
    if (!loading && session && isPlatformAdmin && !pathname.startsWith("/platform")) {
      navigate({ to: "/platform", replace: true });
    }
    if (!loading && session && !isPlatformAdmin && pathname.startsWith("/platform")) {
      navigate({ to: "/dashboard", replace: true });
    }
  }, [loading, session, isPlatformAdmin, pathname, navigate]);

  if (loading || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="border-primary size-8 animate-spin rounded-full border-2 border-t-transparent" />
      </div>
    );
  }

  if (session.user.must_change_password) {
    return (
      <main className="min-h-screen px-4 py-10">
        <Outlet />
      </main>
    );
  }

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full min-w-0" data-language={language}>
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="bg-card/90 sticky top-0 z-10 flex h-14 min-w-0 shrink-0 items-center gap-2 border-b px-2 backdrop-blur print:hidden sm:px-4">
            <div className="flex min-w-0 shrink-0 items-center gap-2">
              <SidebarTrigger />
              <Link
                to={isPlatformAdmin ? "/platform" : "/dashboard"}
                className="flex min-w-0 items-center gap-2"
              >
                <img
                  src={brandLogo}
                  alt={t("landing.logoAlt")}
                  className="h-7 w-20 shrink-0 object-contain sm:w-24"
                />
                {!isPlatformAdmin && (
                  <div className="hidden min-w-0 leading-tight sm:block">
                    <p className="font-display max-w-40 truncate text-sm font-bold uppercase">
                      {settings.companyName}
                    </p>
                    <p className="text-muted-foreground max-w-40 truncate text-[11px]">
                      {settings.address}
                    </p>
                  </div>
                )}
                {isPlatformAdmin && (
                  <span className="hidden truncate text-sm font-semibold sm:inline">
                    {t("platform.title")}
                  </span>
                )}
              </Link>
            </div>
            {!isPlatformAdmin && can("products.view") && (
              <>
                <form
                  className="mx-auto hidden w-full max-w-md flex-1 items-center gap-2 md:flex"
                  role="search"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const query = search.trim();
                    if (query.length >= 2) {
                      void navigate({ to: "/recherche", search: { q: query } });
                    }
                  }}
                >
                  <Input
                    type="search"
                    aria-label={t("search.inputLabel")}
                    placeholder={t("search.placeholder")}
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    className="h-9"
                  />
                  <Button
                    type="submit"
                    size="icon"
                    variant="outline"
                    className="size-9 shrink-0"
                    aria-label={t("search.submit")}
                    title={t("search.submit")}
                    disabled={search.trim().length < 2}
                  >
                    <Search className="size-4" />
                  </Button>
                </form>
                <Button
                  asChild
                  variant="ghost"
                  size="icon"
                  className="size-9 md:hidden"
                  aria-label={t("search.title")}
                  title={t("search.title")}
                >
                  <Link to="/recherche" search={{ q: "" }}>
                    <Search className="size-5" />
                  </Link>
                </Button>
              </>
            )}
            <nav
              aria-label={t("nav.management")}
              className="ml-auto flex shrink-0 items-center justify-end gap-1 sm:gap-2"
            >
              {can("notifications.view") && <NotificationBell />}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-9 rounded-full"
                    aria-label={t("nav.profile")}
                    title={t("nav.profile")}
                  >
                    <UserRound className="size-5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-60">
                  <DropdownMenuLabel className="font-normal">
                    <p className="truncate text-sm font-medium">{fullName || session.user.email}</p>
                    <p className="text-muted-foreground truncate text-xs">
                      {isPlatformAdmin
                        ? t("platform.ownerRole")
                        : roles
                            .map((role) => t(role === "stock" ? "role.manager" : `role.${role}`))
                            .join(" + ")}
                    </p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {can("profile.view") && (
                    <DropdownMenuItem asChild>
                      <Link to="/profil">{t("nav.profile")}</Link>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem
                    onSelect={() => {
                      void signOut();
                    }}
                  >
                    <LogOut className="size-4" />
                    {t("nav.signOut")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </nav>
          </header>

          <main className="min-w-0 flex-1 p-3 sm:p-4 md:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
