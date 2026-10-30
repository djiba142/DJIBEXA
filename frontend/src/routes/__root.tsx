import type { ErrorComponentProps } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  useRouterState,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import { Toaster } from "../components/ui/sonner";
import { AuthProvider } from "../lib/auth";
import { LocaleProvider, useLocale } from "../lib/locale";
import appCss from "../styles.css?url";

function NotFoundComponent() {
  const { t } = useLocale();
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">{t("common.notFound")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("common.notFoundDescription")}</p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t("common.home")}
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  const { t } = useLocale();
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    console.error("Erreur de rendu de l’application", error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          {t("common.errorTitle")}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("common.errorDescription")}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t("common.retry")}
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            {t("common.home")}
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "ERP DJIBEXA" },
      { name: "description", content: "Gestion commerciale, ventes et stocks." },
      { name: "author", content: "DJIBEXA" },
      { property: "og:title", content: "ERP DJIBEXA" },
      { property: "og:description", content: "Gestion commerciale, ventes et stocks." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
      { rel: "icon", href: "/brand/kourouma-mark.svg", type: "image/svg+xml" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LocaleProvider>
          <LocalizedPageTitle pathname={pathname} />
          {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
          <Outlet />
          <Toaster position="top-right" richColors />
        </LocaleProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

function LocalizedPageTitle({ pathname }: { pathname: string }) {
  const { t } = useLocale();
  const pageTitles: [string, string][] = [
    ["/change-password", "auth.changePasswordTitle"],
    ["/dashboard", "nav.dashboard"],
    ["/ventes/nouvelle", "nav.newSale"],
    ["/ventes", "nav.sales"],
    ["/devis-clients", "nav.customerQuotes"],
    ["/recherche", "nav.smartSearch"],
    ["/produits", "nav.products"],
    ["/stock-manuel", "nav.manualStock"],
    ["/stock", "nav.stock"],
    ["/inventaire", "nav.inventory"],
    ["/entrepots", "nav.warehouses"],
    ["/commandes", "nav.orders"],
    ["/receptions", "nav.receipts"],
    ["/livraisons", "nav.deliveries"],
    ["/notifications", "nav.notifications"],
    ["/credits", "nav.credits"],
    ["/clients", "nav.customers"],
    ["/partenaires", "nav.partners"],
    ["/rapports-inventaire", "nav.inventoryReports"],
    ["/rapports", "nav.reports"],
    ["/utilisateurs", "nav.users"],
    ["/parametres", "nav.settings"],
    ["/mise-en-service", "nav.setupGuide"],
    ["/profil", "nav.profile"],
    ["/aide", "nav.help"],
  ];
  const key = pageTitles.find(
    ([path]) => pathname === path || pathname.startsWith(`${path}/`),
  )?.[1];

  useEffect(() => {
    if (!key) return;
    const title = `${t(key)} — DJIBEXA`;
    document.title = title;
    const openGraphTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    if (openGraphTitle) openGraphTitle.content = title;
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = t("app.pageDescription");
    const openGraphDescription = document.querySelector<HTMLMetaElement>(
      'meta[property="og:description"]',
    );
    if (openGraphDescription) openGraphDescription.content = t("app.pageDescription");
  }, [key, t]);

  return null;
}
