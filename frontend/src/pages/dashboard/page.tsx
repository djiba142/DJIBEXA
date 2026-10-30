import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import {
  Activity,
  AlertTriangle,
  CircleHelp,
  ClipboardCheck,
  Package,
  Receipt,
  Search,
  ShoppingCart,
  TrendingUp,
  TrendingDown,
  WalletCards,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/dashboard")({
  head: () => ({
    meta: [
      { title: "Tableau de bord — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Chiffre d'affaires du jour, ventes récentes et alertes de stock en un coup d'œil.",
      },
      { property: "og:title", content: "Tableau de bord — DJIBEXA" },
      {
        property: "og:description",
        content: "Suivi quotidien des ventes et du stock du magasin.",
      },
    ],
  }),
  component: Dashboard,
});

function dashboardDateOffset(date: string, offset: number) {
  const result = new Date(`${date}T12:00:00Z`);
  result.setUTCDate(result.getUTCDate() + offset);
  return result.toISOString().slice(0, 10);
}

function Dashboard() {
  const navigate = useNavigate();
  const { fullName, role, can, hasRole } = useAuth();
  const { t, language } = useLocale();
  const [quickSearch, setQuickSearch] = useState("");
  const isSales = hasRole("sales") && !hasRole("admin");
  const canViewSales = can("sales.view");
  const canViewProducts = can("products.view");
  const canViewCustomers = can("customers.view");
  const canViewOperations = can("receptions.view") || can("inventory.view");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard-overview", role],
    queryFn: () =>
      api.get<{
        date: string;
        timezone: string;
        currency: string;
        sales_amount: number | null;
        sales_count: number | null;
        collected_amount: number | null;
        returned_amount: number | null;
        sold_references: number | null;
        stock_alert_count: number;
        out_of_stock_count?: number | null;
        pending_receipts: number | null;
        draft_receipts: number | null;
        pending_inventory_counts: number | null;
        pending_return_quarantines: number | null;
        pending_customer_quotes?: number | null;
        confirmed_customer_orders?: number | null;
        low_stock: {
          id: number;
          name: string;
          reference: string;
          stock: number;
          threshold: number;
        }[];
        recent_sales: {
          id: number;
          invoice_number: string | null;
          customer_name: string;
          sale_date: string;
          status: "paid" | "partial";
          amount: number;
        }[];
        pending_return_items?: {
          id: number;
          sale_id: number;
          invoice_number: string | null;
          product_name: string;
          location_name: string;
          quantity_remaining: number;
          reason: string;
        }[];
        sales_trend:
          | {
              date: string;
              sales: number;
              sales_count: number;
            }[]
          | null;
      }>("dashboard/overview/"),
  });
  const financeQuery = useQuery({
    queryKey: ["dashboard-finance", data?.date],
    queryFn: () => {
      if (!data?.date) throw new Error(t("dashboard.financeLoadFailed"));
      return api.get<{
        outstanding_balance: number;
        outstanding_balance_scope: "current_open_credit_sales";
        external_supplier_payables: number;
        external_supplier_payables_scope: "confirmed_external_purchases_after_validated_payments";
        cash_out: number;
        net_cash: number;
      }>("reports/finance/", { start_date: data.date, end_date: data.date });
    },
    enabled: hasRole("admin") && can("reports.view") && Boolean(data?.date),
  });
  const trendFallbackQuery = useQuery({
    queryKey: ["dashboard-sales-trend", data?.date, role],
    queryFn: () => {
      if (!data?.date) throw new Error(t("dashboard.loadFailed"));
      return api.get<{
        sales_trend: {
          period: string;
          sales: number | string;
          sales_count: number;
        }[];
      }>("reports/sales/", {
        start_date: dashboardDateOffset(data.date, -6),
        end_date: data.date,
        period: "day",
      });
    },
    enabled: canViewSales && !isSales && Boolean(data?.date) && data?.sales_trend == null,
  });
  const canViewFinancialOverview = hasRole("admin") && can("reports.view");

  const cards: {
    label: string;
    value: string;
    icon: typeof TrendingUp;
    to?: "/stock" | "/receptions" | "/inventaire";
  }[] = [
    ...(canViewSales
      ? [
          {
            label: t("dashboard.revenueToday"),
            value: isLoading || isError ? "—" : money(data?.sales_amount ?? 0),
            icon: TrendingUp,
          },
          {
            label: t("dashboard.salesToday"),
            value: isLoading || isError ? "—" : String(data?.sales_count ?? 0),
            icon: Receipt,
          },
          {
            label: t("dashboard.collectedToday"),
            value: isLoading || isError ? "—" : money(data?.collected_amount ?? 0),
            icon: WalletCards,
          },
          {
            label: t("dashboard.soldReferences"),
            value: isLoading || isError ? "—" : String(data?.sold_references ?? 0),
            icon: Package,
          },
        ]
      : []),
    ...(canViewProducts
      ? [
          {
            label: t("dashboard.stockAlerts"),
            value: isLoading || isError ? "—" : String(data?.stock_alert_count ?? 0),
            icon: AlertTriangle,
            to: "/stock" as const,
          },
          ...(typeof data?.out_of_stock_count === "number"
            ? [
                {
                  label: t("dashboard.outOfStock"),
                  value: isLoading || isError ? "—" : String(data.out_of_stock_count),
                  icon: Package,
                  to: "/stock" as const,
                },
              ]
            : []),
        ]
      : []),
    ...(canViewOperations
      ? [
          {
            label: t("dashboard.pendingReceipts"),
            value: isLoading || isError ? "—" : String(data?.pending_receipts ?? 0),
            icon: ClipboardCheck,
            to: "/receptions" as const,
          },
          {
            label: t("dashboard.pendingInventories"),
            value: isLoading || isError ? "—" : String(data?.pending_inventory_counts ?? 0),
            icon: ClipboardCheck,
            to: "/inventaire" as const,
          },
        ]
      : []),
    ...(hasRole("admin") && data?.pending_return_quarantines !== null
      ? [
          {
            label: t("dashboard.pendingReturnChecks"),
            value: isLoading || isError ? "—" : String(data?.pending_return_quarantines ?? 0),
            icon: AlertTriangle,
          },
        ]
      : []),
  ];
  const salesTrend =
    data?.sales_trend ??
    (() => {
      if (!data?.date || !trendFallbackQuery.data) return undefined;
      return Array.from({ length: 7 }, (_, offset) => {
        const date = dashboardDateOffset(data.date, offset - 6);
        const reportDay = trendFallbackQuery.data.sales_trend.find(
          (entry) => entry.period.slice(0, 10) === date,
        );
        return {
          date,
          sales: Number(reportDay?.sales ?? 0),
          sales_count: reportDay?.sales_count ?? 0,
        };
      });
    })();
  const maxDashboardTrendSales = Math.max(...(salesTrend ?? []).map((day) => Number(day.sales)), 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("nav.dashboard")}</h1>
          <p className="text-muted-foreground text-sm">
            {t("dashboard.greeting", { name: fullName || t("dashboard.welcome") })}
          </p>
          <p className="text-muted-foreground mt-1 text-xs">
            {isLoading
              ? t("dashboard.loading")
              : t("dashboard.period", {
                  date: data?.date ?? "—",
                  timezone: data?.timezone ?? "",
                })}
          </p>
        </div>
        {canViewProducts && (
          <form
            className="flex w-full max-w-xl items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const query = quickSearch.trim();
              if (query.length >= 2) {
                void navigate({ to: "/recherche", search: { q: query } });
              }
            }}
          >
            <div className="min-w-0 flex-1 space-y-1.5">
              <label htmlFor="dashboard-part-search" className="text-sm font-medium">
                {t("search.inputLabel")}
              </label>
              <Input
                id="dashboard-part-search"
                type="search"
                className="h-11"
                placeholder={t("search.placeholder")}
                value={quickSearch}
                onChange={(event) => setQuickSearch(event.target.value)}
              />
            </div>
            <Button type="submit" className="h-11" disabled={quickSearch.trim().length < 2}>
              <Search className="size-4" /> {t("search.submit")}
            </Button>
          </form>
        )}
      </div>

      {isError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm"
        >
          <span>{t("dashboard.loadFailed")}</span>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      )}

      {canViewFinancialOverview && financeQuery.isError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm"
        >
          <span>{t("dashboard.financeLoadFailed")}</span>
          <Button variant="outline" size="sm" onClick={() => void financeQuery.refetch()}>
            {t("common.retry")}
          </Button>
        </div>
      )}

      {isSales ? (
        <nav aria-label={t("nav.management")} className="grid gap-3 sm:grid-cols-2">
          <Button
            asChild
            size="lg"
            className="h-20 justify-start gap-4 px-5 text-base font-semibold"
          >
            <Link to="/ventes/nouvelle">
              <ShoppingCart className="size-7 shrink-0" />
              {t("dashboard.newSale")}
            </Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="h-20 justify-start gap-4 px-5 text-base font-semibold"
          >
            <Link to="/ventes">
              <Receipt className="size-7 shrink-0" />
              {t("nav.sales")}
            </Link>
          </Button>
          {canViewCustomers && (
            <Button
              asChild
              size="lg"
              variant="outline"
              className="h-20 justify-start gap-4 px-5 text-base font-semibold"
            >
              <Link to="/clients">
                <Package className="size-7 shrink-0" />
                {t("nav.customers")}
              </Link>
            </Button>
          )}
          {can("credits.view") && (
            <Button
              asChild
              size="lg"
              variant="outline"
              className="h-20 justify-start gap-4 px-5 text-base font-semibold"
            >
              <Link to="/credits">
                <WalletCards className="size-7 shrink-0" />
                {t("nav.credits")}
              </Link>
            </Button>
          )}
          <Button
            asChild
            size="lg"
            variant="outline"
            className="h-20 justify-start gap-4 px-5 text-base font-semibold"
          >
            <Link to="/aide">
              <CircleHelp className="size-7 shrink-0" />
              {t("nav.help")}
            </Link>
          </Button>
        </nav>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {cards.map((c) => {
            const card = (
              <>
                <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                  <c.icon className="size-4" />
                  {c.label}
                </div>
                <p className="font-display mt-2 text-2xl font-bold">{c.value}</p>
              </>
            );
            return c.to ? (
              <Link
                key={c.label}
                to={c.to}
                className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {card}
              </Link>
            ) : (
              <div key={c.label} className="panel p-4">
                {card}
              </div>
            );
          })}
        </div>
      )}

      {canViewFinancialOverview && (
        <section className="space-y-3" aria-labelledby="dashboard-finances">
          <div>
            <h2 id="dashboard-finances" className="text-lg font-bold uppercase">
              {t("dashboard.financialPosition")}
            </h2>
            <p className="text-muted-foreground text-xs">{t("dashboard.financialPositionHelp")}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Link
              to="/credits"
              className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                <WalletCards className="size-4" />
                {t("dashboard.customerReceivables")}
              </div>
              <p className="font-display mt-2 text-2xl font-bold">
                {financeQuery.isLoading || financeQuery.isError || !financeQuery.data
                  ? "—"
                  : money(financeQuery.data?.outstanding_balance ?? 0)}
              </p>
              <p className="text-muted-foreground mt-1 text-xs">
                {t("dashboard.customerReceivablesHelp")}
              </p>
            </Link>
            <Link
              to="/credits"
              search={{ tab: "suppliers" }}
              className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                <WalletCards className="size-4" />
                {t("dashboard.supplierPayables")}
              </div>
              <p className="font-display mt-2 text-2xl font-bold">
                {financeQuery.isLoading || financeQuery.isError || !financeQuery.data
                  ? "—"
                  : money(financeQuery.data?.external_supplier_payables ?? 0)}
              </p>
              <p className="text-muted-foreground mt-1 text-xs">
                {t("dashboard.supplierPayablesHelp")}
              </p>
            </Link>
            <Link
              to="/rapports"
              className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                <TrendingDown className="size-4" />
                {t("dashboard.expensesToday")}
              </div>
              <p className="font-display mt-2 text-2xl font-bold">
                {financeQuery.isLoading || financeQuery.isError || !financeQuery.data
                  ? "—"
                  : money(financeQuery.data.cash_out)}
              </p>
              <p className="text-muted-foreground mt-1 text-xs">
                {t("dashboard.expensesTodayHelp")}
              </p>
            </Link>
            <Link
              to="/rapports"
              className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                <Activity className="size-4" />
                {t("dashboard.netCashflowToday")}
              </div>
              <p className="font-display mt-2 text-2xl font-bold">
                {financeQuery.isLoading || financeQuery.isError || !financeQuery.data
                  ? "—"
                  : money(financeQuery.data.net_cash)}
              </p>
              <p className="text-muted-foreground mt-1 text-xs">
                {t("dashboard.netCashflowTodayHelp")}
              </p>
            </Link>
          </div>
        </section>
      )}

      {hasRole("admin") &&
        (typeof data?.pending_customer_quotes === "number" ||
          typeof data?.confirmed_customer_orders === "number") && (
          <section className="space-y-3" aria-labelledby="dashboard-customer-orders">
            <h2 id="dashboard-customer-orders" className="text-lg font-bold uppercase">
              {t("dashboard.customerOrders")}
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {typeof data.pending_customer_quotes === "number" && (
                <Link
                  to="/devis-clients"
                  className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                    <Receipt className="size-4" />
                    {t("dashboard.unconfirmedQuotes")}
                  </div>
                  <p className="font-display mt-2 text-2xl font-bold">
                    {data.pending_customer_quotes}
                  </p>
                </Link>
              )}
              {typeof data.confirmed_customer_orders === "number" && (
                <Link
                  to="/devis-clients"
                  className="panel block p-4 transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
                    <ClipboardCheck className="size-4" />
                    {t("dashboard.confirmedOrders")}
                  </div>
                  <p className="font-display mt-2 text-2xl font-bold">
                    {data.confirmed_customer_orders}
                  </p>
                </Link>
              )}
            </div>
          </section>
        )}

      {canViewSales && !isSales && salesTrend && (
        <section className="panel space-y-3 p-4" aria-labelledby="dashboard-sales-trend">
          <div>
            <h2 id="dashboard-sales-trend" className="text-lg font-bold uppercase">
              {t("dashboard.salesTrend")}
            </h2>
            <p className="text-muted-foreground text-xs">{t("dashboard.salesTrendHelp")}</p>
          </div>
          <div
            role="img"
            aria-label={t("dashboard.salesTrend")}
            className="grid grid-cols-7 items-end gap-2"
          >
            {salesTrend.map((day) => {
              const value = Number(day.sales);
              const height =
                maxDashboardTrendSales > 0 ? (value / maxDashboardTrendSales) * 100 : 0;
              return (
                <div
                  key={day.date}
                  className="flex min-w-0 flex-col items-center gap-2"
                  title={`${day.date}: ${money(value)} · ${day.sales_count}`}
                  aria-label={`${day.date}: ${money(value)} · ${day.sales_count}`}
                >
                  <span className="text-muted-foreground truncate text-center text-[10px] sm:text-xs">
                    {new Intl.NumberFormat(undefined, {
                      notation: "compact",
                      maximumFractionDigits: 1,
                    }).format(value)}
                  </span>
                  <div className="bg-muted flex h-32 w-full items-end overflow-hidden rounded-sm">
                    <div
                      className="bg-primary w-full rounded-sm transition-[height]"
                      style={{ height: `${height}%` }}
                    />
                  </div>
                  <span className="text-muted-foreground text-center text-[10px] sm:text-xs">
                    {new Intl.DateTimeFormat(language, { weekday: "short" }).format(
                      new Date(`${day.date}T12:00:00`),
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <div className={canViewSales && canViewProducts ? "grid gap-4 lg:grid-cols-2" : "grid gap-4"}>
        {canViewSales && (
          <div className="panel p-4">
            <div className="mb-3 flex items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-bold uppercase">{t("dashboard.recentSales")}</h2>
                <p className="text-muted-foreground text-xs">{t("dashboard.periodTodayOnly")}</p>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link to="/ventes">{t("nav.sales")}</Link>
              </Button>
            </div>
            <ul className="divide-border divide-y">
              {(data?.recent_sales ?? []).map((sale) => (
                <li key={sale.id}>
                  <Link
                    to="/ventes/$saleId"
                    params={{ saleId: String(sale.id) }}
                    className="hover:bg-accent flex items-center justify-between gap-3 rounded-md py-2 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="font-medium">{sale.invoice_number ?? `VTE-${sale.id}`}</p>
                      <p className="text-muted-foreground truncate text-xs">
                        {sale.customer_name || t("dashboard.counterCustomer")} ·{" "}
                        {dateTime(sale.sale_date)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Badge variant={sale.status === "paid" ? "secondary" : "outline"}>
                        {t(`reports.saleStatus.${sale.status}`)}
                      </Badge>
                      <span className="font-semibold">{money(sale.amount)}</span>
                    </div>
                  </Link>
                </li>
              ))}
              {isLoading ? (
                <li className="text-muted-foreground py-6 text-center text-sm">
                  {t("dashboard.loading")}
                </li>
              ) : !isError && !data?.recent_sales.length ? (
                <li className="text-muted-foreground py-6 text-center text-sm">
                  {t("dashboard.noSales")}
                </li>
              ) : null}
            </ul>
          </div>
        )}

        {canViewProducts && !isSales && (
          <div className="panel p-4">
            <h2 className="mb-3 text-lg font-bold uppercase">{t("dashboard.lowStock")}</h2>
            <ul className="divide-border divide-y">
              {(data?.low_stock ?? []).slice(0, 8).map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{p.name}</p>
                    <p className="text-muted-foreground text-xs">{p.reference}</p>
                  </div>
                  <Badge variant={p.stock === 0 ? "destructive" : "secondary"}>
                    {p.stock} {t("dashboard.inStock")}
                  </Badge>
                </li>
              ))}
              {isLoading ? (
                <li className="text-muted-foreground py-6 text-center text-sm">
                  {t("dashboard.loading")}
                </li>
              ) : !isError && !data?.stock_alert_count ? (
                <li className="text-muted-foreground py-6 text-center text-sm">
                  {t("dashboard.emptyStock")}
                </li>
              ) : null}
            </ul>
          </div>
        )}
      </div>

      {hasRole("admin") && Boolean(data?.pending_return_items?.length) && (
        <section className="panel space-y-3 p-4">
          <h2 className="text-lg font-bold uppercase">{t("dashboard.pendingReturnItems")}</h2>
          <ul className="divide-border divide-y">
            {data?.pending_return_items?.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
              >
                <div className="min-w-0">
                  <p className="font-medium">{item.product_name}</p>
                  <p className="text-muted-foreground text-xs">
                    {item.location_name} · {item.quantity_remaining} · {item.reason}
                  </p>
                </div>
                <Button asChild variant="outline" size="sm">
                  <Link to="/ventes/$saleId" params={{ saleId: String(item.sale_id) }}>
                    {item.invoice_number ?? `VTE-${item.sale_id}`} · {t("dashboard.reviewReturn")}
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
