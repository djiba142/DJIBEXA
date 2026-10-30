import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Circle,
  ClipboardCheck,
  Package,
  Users,
  Warehouse,
} from "lucide-react";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/mise-en-service")({
  head: () => ({
    meta: [
      { title: "Mise en service — ERP DJIBEXA" },
      {
        name: "description",
        content: "Guide de configuration initiale de l'entreprise, des boutiques et du stock.",
      },
    ],
  }),
  component: () => (
    <RequirePermission permission="users.manage">
      <SetupGuide />
    </RequirePermission>
  ),
});

type InvoiceBranding = {
  company_name: string;
  activity: string;
  address: string;
  phone_numbers: string[];
  is_configured: boolean;
};

type LocationRow = {
  id: number;
  name: string;
  location_type: string;
  is_active: boolean;
};

type UserRow = {
  id: number;
  is_active: boolean;
  roles: string[];
};

type ProductRow = {
  id: number;
  is_active: boolean;
};

type StockRow = {
  id: number;
  product: number;
  location: number;
  quantity: number;
};

type ReservedOrder = {
  location: number;
  items: { product: number; quantity: number }[];
};

function SetupGuide() {
  const { t } = useLocale();
  const setupQuery = useQuery({
    queryKey: ["setup-guide-status"],
    queryFn: async () => {
      const [branding, locations, users, products, stock, confirmedOrders] = await Promise.all([
        api.get<InvoiceBranding>("invoices/branding/"),
        api.list<LocationRow>("inventory/locations/"),
        api.list<UserRow>("users/"),
        api.list<ProductRow>("products/"),
        api.list<StockRow>("inventory/stock/"),
        api.list<ReservedOrder>("sales/customer-orders/", { status: "confirmed" }),
      ]);
      return { branding, locations, users, products, stock, confirmedOrders };
    },
  });

  const setup = setupQuery.data;
  const activeShops = setup?.locations.filter(
    (location) => location.is_active && location.location_type === "shop",
  );
  const activeUsers = setup?.users.filter((user) => user.is_active);
  const activeProducts = setup?.products.filter((product) => product.is_active);
  const shopIds = new Set((activeShops ?? []).map((location) => location.id));
  const reservations = new Map<string, number>();
  for (const order of setup?.confirmedOrders ?? []) {
    for (const item of order.items) {
      const key = `${order.location}:${item.product}`;
      reservations.set(key, (reservations.get(key) ?? 0) + item.quantity);
    }
  }
  const saleableRows = (setup?.stock ?? [])
    .map((stock) => ({
      ...stock,
      availableQuantity: Math.max(
        0,
        stock.quantity - (reservations.get(`${stock.location}:${stock.product}`) ?? 0),
      ),
    }))
    .filter((stock) => shopIds.has(stock.location) && stock.availableQuantity > 0);
  const saleableUnits = saleableRows.reduce((total, stock) => total + stock.availableQuantity, 0);
  const brandingComplete = Boolean(
    setup?.branding.is_configured &&
    setup.branding.company_name.trim() &&
    setup.branding.address.trim() &&
    setup.branding.phone_numbers.some((phone) => phone.trim()),
  );

  const steps = [
    {
      key: "company",
      icon: Building2,
      title: t("setup.company.title"),
      description: t("setup.company.description"),
      detail: t("setup.company.detail"),
      to: "/parametres" as const,
      complete: brandingComplete,
      required: true,
    },
    {
      key: "shops",
      icon: Warehouse,
      title: t("setup.shops.title"),
      description: t("setup.shops.description"),
      detail: t("setup.shops.count", { count: formatNumber(activeShops?.length ?? 0) }),
      to: "/entrepots" as const,
      complete: Boolean(activeShops?.length),
      required: true,
    },
    {
      key: "users",
      icon: Users,
      title: t("setup.users.title"),
      description: t("setup.users.description"),
      detail: t("setup.users.count", { count: formatNumber(activeUsers?.length ?? 0) }),
      to: "/utilisateurs" as const,
      complete: Boolean(activeUsers && activeUsers.length > 1),
      required: false,
    },
    {
      key: "products",
      icon: Package,
      title: t("setup.products.title"),
      description: t("setup.products.description"),
      detail: t("setup.products.count", { count: formatNumber(activeProducts?.length ?? 0) }),
      to: "/produits" as const,
      complete: Boolean(activeProducts?.length),
      required: true,
    },
    {
      key: "stock",
      icon: ClipboardCheck,
      title: t("setup.stock.title"),
      description: t("setup.stock.description"),
      detail: t("setup.stock.count", {
        products: formatNumber(saleableRows.length),
        units: formatNumber(saleableUnits),
      }),
      to: "/inventaire" as const,
      complete: Boolean(saleableRows.length),
      required: true,
    },
  ];

  const requiredSteps = steps.filter((step) => step.required);
  const completedSteps = requiredSteps.filter((step) => step.complete).length;
  const progress = requiredSteps.length
    ? Math.round((completedSteps / requiredSteps.length) * 100)
    : 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold uppercase">{t("setup.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("setup.description")}</p>
      </header>

      <section className="panel space-y-4 p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-medium">{t("setup.progress")}</p>
            <p className="mt-1 text-2xl font-bold">
              {!setup
                ? "—"
                : t("setup.progressCount", {
                    completed: formatNumber(completedSteps),
                    total: formatNumber(requiredSteps.length),
                  })}
            </p>
          </div>
          {!setupQuery.isLoading && !setupQuery.isError && (
            <Badge variant={progress === 100 ? "default" : "secondary"}>
              {progress === 100 ? t("setup.ready") : t("setup.inProgress")}
            </Badge>
          )}
        </div>
        <div
          className="h-2 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label={t("setup.progress")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={setup ? progress : 0}
        >
          <div
            className="h-full rounded-full bg-primary transition-[width]"
            style={{ width: `${setup ? progress : 0}%` }}
          />
        </div>
        <p className="text-sm text-muted-foreground">{t("setup.progressHint")}</p>
      </section>

      {setupQuery.isError && (
        <section className="panel flex flex-wrap items-center justify-between gap-3 border-destructive/40 p-4">
          <p className="text-sm text-destructive">{t("setup.loadFailed")}</p>
          <Button variant="outline" onClick={() => void setupQuery.refetch()}>
            {t("common.retry")}
          </Button>
        </section>
      )}

      <ol className="space-y-3">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <li key={step.key}>
              <section className="panel flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:p-5">
                <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Icon className="size-5" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t("setup.step", { number: formatNumber(index + 1) })}
                    </span>
                    {!step.required && <Badge variant="outline">{t("setup.optional")}</Badge>}
                  </div>
                  <h2 className="font-semibold">{step.title}</h2>
                  <p className="text-sm text-muted-foreground">{step.description}</p>
                  {setup && (
                    <p className="text-xs text-muted-foreground" aria-live="polite">
                      {step.detail}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-3 sm:justify-end">
                  {setup && (
                    <span
                      className={`inline-flex items-center gap-1.5 text-sm ${
                        step.complete ? "text-emerald-700" : "text-muted-foreground"
                      }`}
                    >
                      {step.complete ? (
                        <CheckCircle2 className="size-4" aria-hidden="true" />
                      ) : (
                        <Circle className="size-4" aria-hidden="true" />
                      )}
                      {step.complete ? t("setup.complete") : t("setup.pending")}
                    </span>
                  )}
                  <Button
                    asChild
                    size="sm"
                    variant={setup && step.complete ? "outline" : "default"}
                  >
                    <Link to={step.to}>
                      {setup && step.complete ? t("setup.review") : t("setup.open")}
                      <ArrowRight aria-hidden="true" />
                    </Link>
                  </Button>
                </div>
              </section>
            </li>
          );
        })}
      </ol>

      <section className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4">
        <h2 className="font-semibold">{t("setup.stockSafetyTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("setup.stockSafetyDescription")}</p>
      </section>
    </div>
  );
}
