import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Download, LineChart, Receipt, TrendingUp, Truck } from "lucide-react";
import { useMemo, useState } from "react";

import { RequirePermission } from "@/components/RequirePermission";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatNumber, money, shortDate } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/rapports")({
  head: () => ({
    meta: [
      { title: "Rapports & statistiques — ERP DJIBEXA" },
      {
        name: "description",
        content: "Analyse des ventes, des produits et des encaissements depuis les données ERP.",
      },
      { property: "og:title", content: "Rapports & statistiques — DJIBEXA" },
      {
        property: "og:description",
        content: "Analysez les ventes et les tendances avec les indicateurs du système.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequirePermission permission="sales.view">
      <Rapports />
    </RequirePermission>
  ),
});

type ReportValue = number | string;
type SalesReport = {
  summary: {
    total_sales: ReportValue;
    total_received: ReportValue;
    outstanding_balance: ReportValue;
    sales_count: number;
    average_basket: ReportValue;
    total_discount: ReportValue;
    total_customers: number;
    total_products: number;
    total_quantity_sold: number;
    returned_amount: ReportValue;
    returned_quantity: number;
    total_cost?: ReportValue | null;
    gross_margin?: ReportValue | null;
    gross_margin_percent?: ReportValue;
    profitability?: { available: boolean; reason: string };
  };
  top_products: {
    id: number;
    name: string;
    sku: string;
    quantity_sold: number;
    revenue: ReportValue;
  }[];
  sales_trend: {
    period: string;
    sales: ReportValue;
    sales_count: number;
    received: ReportValue;
  }[];
  sales_by_seller: {
    seller_id: number | null;
    seller_name: string;
    sale_count: number;
    total_sales: ReportValue;
  }[];
  sales_by_location?: {
    location_id: number | null;
    location_name: string | null;
    location_type: string | null;
    sale_count: number;
    total_sales: ReportValue;
  }[];
  sales_by_payment_method: {
    payment_method: string;
    sale_count: number;
    total_sales: ReportValue;
  }[];
  sales_by_status: { status: string; sale_count: number; total_sales: ReportValue }[];
  customer_breakdown: {
    customer_id: number;
    customer__full_name: string;
    total_sales: ReportValue;
  }[];
  inventory_status: {
    total_stock_items: number;
    low_stock_products: number;
    healthy_products: number;
    inventory_value?: ReportValue;
    average_margin_percent?: number;
    low_margin_products?: {
      id: number;
      name: string;
      sku: string;
      quantity: number;
      cost_price: number;
      selling_price: number;
      margin_percent: number;
    }[];
    financial_data_quality?: {
      products_with_cost: number;
      products_missing_cost: number;
      cost_coverage_percent: number;
    };
  };
};

type PurchaseReport = {
  summary: {
    order_count: number;
    ordered_amount: number;
    receipt_count: number;
    received_quantity: number;
    received_amount: number;
    supplier_count: number;
    acquisition_costs: number;
    ordered_amount_is_not_stock: boolean;
  };
  suppliers: {
    supplier_id: number;
    supplier: string;
    order_count: number;
    ordered_quantity: number;
    ordered_amount: number;
    receipt_count: number;
    received_quantity: number;
    received_amount: number;
    currency_comparison_available: boolean;
  }[];
  suppliers_truncated: boolean;
  data_quality: {
    currency_comparison_available: boolean;
    currency_comparison_reason: string;
  };
};

type CreditCustomer = {
  customer_id: number;
  customer_name: string;
  sales_count: number;
  total_credit: ReportValue;
  total_paid: ReportValue;
  balance: ReportValue;
  aging_bucket: "0-30" | "31-60" | "61-90" | "90+" | "paid";
  days_overdue: number;
  oldest_open_credit_date: string | null;
};

type FinanceReport = {
  cash_in: number;
  cash_out: number;
  net_cash: number;
  outstanding_balance: number;
  outstanding_balance_scope: "current_open_credit_sales";
  as_of: string;
};

type ReportSection = "sales" | "purchases" | "credits" | "finance";
type TrendPeriod = "day" | "month";
type SalesFilters = {
  product: string;
  category: string;
  customer: string;
  seller: string;
  location: string;
  paymentMethod: string;
};
type PurchaseFilters = { supplier: string; location: string };

const emptySalesFilters: SalesFilters = {
  product: "",
  category: "",
  customer: "",
  seller: "",
  location: "",
  paymentMethod: "",
};
const emptyPurchaseFilters: PurchaseFilters = { supplier: "", location: "" };

const iso = (date: Date) => date.toISOString().slice(0, 10);

function trendPeriodLabel(value: string, period: TrendPeriod, language: string) {
  if (period === "day") return shortDate(value);
  return new Intl.DateTimeFormat(language, { month: "long", year: "numeric" }).format(
    new Date(`${value.slice(0, 10)}T00:00:00`),
  );
}

function downloadCsv(name: string, rows: (string | number)[][]) {
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(";"))
    .join("\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function Rapports() {
  const { t, language } = useLocale();
  const { can, hasRole } = useAuth();
  const isManagement = hasRole("admin");
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const [from, setFrom] = useState(iso(monthStart));
  const [to, setTo] = useState(iso(today));
  const [trendPeriod, setTrendPeriod] = useState<TrendPeriod>("day");
  const [section, setSection] = useState<ReportSection>("sales");
  const [draftFilters, setDraftFilters] = useState(emptySalesFilters);
  const [salesFilters, setSalesFilters] = useState(emptySalesFilters);
  const [draftPurchaseFilters, setDraftPurchaseFilters] = useState(emptyPurchaseFilters);
  const [purchaseFilters, setPurchaseFilters] = useState(emptyPurchaseFilters);
  const canViewCredits = can("credits.view") && isManagement;
  const canViewFinance = can("reports.view") && isManagement;
  const validRange = Boolean(from && to && from <= to);
  const reportFilters = {
    product_search: salesFilters.product || undefined,
    category_search: salesFilters.category || undefined,
    customer_search: salesFilters.customer || undefined,
    seller_search: salesFilters.seller || undefined,
    location_search: salesFilters.location || undefined,
    payment_method: salesFilters.paymentMethod || undefined,
  };
  const reportQuery = useQuery({
    queryKey: ["rapports", from, to, trendPeriod, salesFilters],
    queryFn: () =>
      api.get<SalesReport>("reports/sales/", {
        start_date: from,
        end_date: to,
        period: trendPeriod,
        ...reportFilters,
      }),
    enabled: validRange && section === "sales",
  });
  const purchasesQuery = useQuery({
    queryKey: ["rapports-purchases", from, to, purchaseFilters],
    queryFn: () =>
      api.get<PurchaseReport>("reports/purchases/", {
        start_date: from,
        end_date: to,
        supplier_search: purchaseFilters.supplier || undefined,
        location_search: purchaseFilters.location || undefined,
      }),
    enabled: validRange && section === "purchases" && can("purchases.view"),
  });
  const creditsQuery = useQuery({
    queryKey: ["rapports-credit-aging"],
    queryFn: () => api.list<CreditCustomer>("payments/credits/"),
    enabled: section === "credits" && canViewCredits,
  });
  const financeQuery = useQuery({
    queryKey: ["rapports-finance", from, to],
    queryFn: () =>
      api.get<FinanceReport>("reports/finance/", {
        start_date: from,
        end_date: to,
      }),
    enabled: validRange && section === "finance" && canViewFinance,
  });
  const data = reportQuery.data;
  const creditSummary = useMemo(() => {
    const customers = creditsQuery.data ?? [];
    const openCredits = customers.filter((customer) => Number(customer.balance) > 0);
    const aging: Record<CreditCustomer["aging_bucket"], number> = {
      "0-30": 0,
      "31-60": 0,
      "61-90": 0,
      "90+": 0,
      paid: 0,
    };
    openCredits.forEach((customer) => {
      aging[customer.aging_bucket] += Number(customer.balance);
    });
    return {
      totalCredit: customers.reduce((total, customer) => total + Number(customer.total_credit), 0),
      totalPaid: customers.reduce((total, customer) => total + Number(customer.total_paid), 0),
      balance: openCredits.reduce((total, customer) => total + Number(customer.balance), 0),
      customerCount: openCredits.length,
      aging,
      openCredits: [...openCredits].sort(
        (left, right) => Number(right.balance) - Number(left.balance),
      ),
    };
  }, [creditsQuery.data]);
  const preset = (days: number) => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - days + 1);
    setTrendPeriod("day");
    setFrom(iso(start));
    setTo(iso(end));
  };
  const annualPreset = () => {
    setTrendPeriod("month");
    setFrom(iso(new Date(today.getFullYear(), 0, 1)));
    setTo(iso(today));
  };
  const salesTrend = useMemo(() => {
    if (!data) return [];
    if (trendPeriod === "day" || !from || !to || from > to) return data.sales_trend;

    const salesByMonth = new Map(
      data.sales_trend.map((entry) => [entry.period.slice(0, 7), entry]),
    );
    const startYear = Number(from.slice(0, 4));
    const startMonth = Number(from.slice(5, 7));
    const endYear = Number(to.slice(0, 4));
    const endMonth = Number(to.slice(5, 7));
    const months: SalesReport["sales_trend"] = [];
    for (let year = startYear; year <= endYear; year += 1) {
      const firstMonth = year === startYear ? startMonth : 1;
      const lastMonth = year === endYear ? endMonth : 12;
      for (let month = firstMonth; month <= lastMonth; month += 1) {
        const key = `${year}-${String(month).padStart(2, "0")}`;
        months.push(
          salesByMonth.get(key) ?? {
            period: `${key}-01`,
            sales: 0,
            sales_count: 0,
            received: 0,
          },
        );
      }
    }
    return months;
  }, [data, from, to, trendPeriod]);

  const cards = [
    {
      label: t("reports.revenue"),
      value: money(data?.summary.total_sales),
      icon: TrendingUp,
    },
    {
      label: t("reports.received"),
      value: money(data?.summary.total_received),
      icon: Receipt,
    },
    {
      label: t("reports.outstanding"),
      value: money(data?.summary.outstanding_balance),
      icon: LineChart,
    },
    {
      label: t("reports.averageBasket"),
      value: money(data?.summary.average_basket),
      icon: Truck,
    },
    {
      label: t("reports.sales"),
      value: formatNumber(data?.summary.sales_count ?? 0),
      icon: Receipt,
    },
    {
      label: t("reports.quantitySold"),
      value: formatNumber(data?.summary.total_quantity_sold ?? 0),
      icon: Truck,
    },
    {
      label: t("reports.returnedAmount"),
      value: money(data?.summary.returned_amount),
      icon: Receipt,
    },
    {
      label: t("reports.returnedQuantity"),
      value: formatNumber(data?.summary.returned_quantity ?? 0),
      icon: Truck,
    },
    {
      label: t("reports.customers"),
      value: formatNumber(data?.summary.total_customers ?? 0),
      icon: Receipt,
    },
    {
      label: t("reports.products"),
      value: formatNumber(data?.summary.total_products ?? 0),
      icon: Truck,
    },
  ];

  const exportReport = () => {
    if (!data) return;
    downloadCsv(`rapport_ventes_${from}_${to}.csv`, [
      [t("reports.from"), from],
      [t("reports.to"), to],
      [t("reports.revenue"), Number(data.summary.total_sales)],
      [t("reports.received"), Number(data.summary.total_received)],
      [t("reports.outstanding"), Number(data.summary.outstanding_balance)],
      [t("reports.averageBasket"), Number(data.summary.average_basket)],
      [t("reports.saleCountLabel"), data.summary.sales_count],
      [t("reports.quantitySold"), data.summary.total_quantity_sold],
      [t("reports.returnedAmount"), Number(data.summary.returned_amount)],
      [t("reports.returnedQuantity"), data.summary.returned_quantity],
      [t("reports.customers"), data.summary.total_customers],
      [t("reports.products"), data.summary.total_products],
      [t("reports.discounts"), Number(data.summary.total_discount)],
      ...(data.summary.profitability
        ? data.summary.profitability.available
          ? [
              [t("reports.totalCost"), Number(data.summary.total_cost ?? 0)],
              [t("reports.grossMargin"), Number(data.summary.gross_margin ?? 0)],
              [t("reports.marginRate"), Number(data.summary.gross_margin_percent ?? 0)],
            ]
          : [[t("reports.profitabilityUnavailable"), data.summary.profitability.reason]]
        : []),
      [t("reports.stockUnits"), data.inventory_status.total_stock_items],
      [t("reports.lowStockProducts"), data.inventory_status.low_stock_products],
      [t("reports.healthyStockProducts"), data.inventory_status.healthy_products],
      ...(canViewFinance
        ? [
            [t("reports.stockValue"), Number(data.inventory_status.inventory_value ?? 0)],
            [t("reports.averageMargin"), Number(data.inventory_status.average_margin_percent ?? 0)],
            [
              t("reports.costCoverage", {
                covered: formatNumber(
                  data.inventory_status.financial_data_quality?.products_with_cost ?? 0,
                ),
                missing: formatNumber(
                  data.inventory_status.financial_data_quality?.products_missing_cost ?? 0,
                ),
                percent: formatNumber(
                  data.inventory_status.financial_data_quality?.cost_coverage_percent ?? 0,
                ),
              }),
            ],
            [],
            [
              t("reports.lowMarginProducts"),
              t("reports.product"),
              t("reports.reference"),
              t("reports.quantity"),
              t("reports.cost"),
              t("reports.sellingPrice"),
              t("reports.marginRate"),
            ],
            ...((data.inventory_status.low_margin_products ?? []).map((product) => [
              product.name,
              product.sku,
              product.quantity,
              product.cost_price,
              product.selling_price,
              product.margin_percent,
            ]) as (string | number)[][]),
          ]
        : []),
      [],
      [
        t(trendPeriod === "month" ? "reports.monthlyRevenue" : "reports.dailyRevenue"),
        t("reports.sales"),
        t("reports.received"),
        t("reports.saleCountLabel"),
      ],
      ...salesTrend.map((entry) => [
        trendPeriodLabel(entry.period, trendPeriod, language),
        Number(entry.sales),
        Number(entry.received),
        entry.sales_count,
      ]),
      [],
      [t("reports.reference"), t("reports.product"), t("reports.quantity"), t("reports.revenue")],
      ...data.top_products.map((product) => [
        product.sku,
        product.name,
        product.quantity_sold,
        Number(product.revenue),
      ]),
      [],
      [t("reports.seller"), t("reports.saleCountLabel"), t("reports.revenue")],
      ...data.sales_by_seller.map((seller) => [
        seller.seller_name || t("reports.unassigned"),
        seller.sale_count,
        Number(seller.total_sales),
      ]),
      [],
      [t("reports.salesByLocation"), t("reports.saleCountLabel"), t("reports.revenue")],
      ...(data.sales_by_location ?? []).map((location) => [
        location.location_name || t("reports.unassignedLocation"),
        location.sale_count,
        Number(location.total_sales),
      ]),
      [],
      [t("reports.paymentMethod"), t("reports.saleCountLabel"), t("reports.revenue")],
      ...data.sales_by_payment_method.map((payment) => [
        t(`reports.paymentMethod.${payment.payment_method}`),
        payment.sale_count,
        Number(payment.total_sales),
      ]),
      [],
      [
        t("reports.salesByStatus"),
        t("reports.status"),
        t("reports.saleCountLabel"),
        t("reports.revenue"),
      ],
      ...data.sales_by_status.map((entry) => [
        t(`reports.saleStatus.${entry.status}`),
        entry.sale_count,
        Number(entry.total_sales),
      ]),
      [],
      [t("reports.customer"), t("reports.revenue")],
      ...data.customer_breakdown.map((customer) => [
        customer.customer__full_name,
        Number(customer.total_sales),
      ]),
    ]);
  };

  const exportPurchases = () => {
    const purchases = purchasesQuery.data;
    if (!purchases) return;
    downloadCsv(`rapport-achats_${from}_${to}.csv`, [
      [t("reports.from"), from],
      [t("reports.to"), to],
      [t("reports.orders"), purchases.summary.order_count],
      [t("reports.orderedAmount"), purchases.summary.ordered_amount],
      [t("reports.receipts"), purchases.summary.receipt_count],
      [t("reports.receivedQuantityLabel"), purchases.summary.received_quantity],
      [t("reports.receivedAmount"), purchases.summary.received_amount],
      [t("reports.supplierCount"), purchases.summary.supplier_count],
      [t("reports.acquisitionCosts"), purchases.summary.acquisition_costs],
      [],
      [
        t("reports.supplier"),
        t("reports.orders"),
        t("reports.orderedAmount"),
        t("reports.orderedQuantity"),
        t("reports.receipts"),
        t("reports.receivedQuantity"),
        t("reports.receivedAmount"),
        t("reports.purchaseCurrencyUnavailable"),
      ],
      ...purchases.suppliers.map((supplier) => [
        supplier.supplier,
        supplier.order_count,
        supplier.ordered_amount,
        supplier.ordered_quantity,
        supplier.receipt_count,
        supplier.received_quantity,
        supplier.received_amount,
        supplier.currency_comparison_available ? t("inventoryReport.yes") : t("inventoryReport.no"),
      ]),
    ]);
  };

  const exportCredits = () => {
    if (!creditsQuery.data) return;
    downloadCsv("rapport-encours-credits.csv", [
      [
        t("reports.customer"),
        t("reports.saleCountLabel"),
        t("reports.creditTotal"),
        t("reports.received"),
        t("reports.outstanding"),
        t("reports.creditAge"),
        t("reports.overdueDays"),
        t("reports.oldestOpenCredit"),
      ],
      ...creditsQuery.data.map((customer) => [
        customer.customer_name,
        customer.sales_count,
        Number(customer.total_credit),
        Number(customer.total_paid),
        Number(customer.balance),
        t(`reports.creditAge.${customer.aging_bucket}`),
        customer.days_overdue,
        customer.oldest_open_credit_date ?? "",
      ]),
    ]);
  };

  const exportFinance = () => {
    const finance = financeQuery.data;
    if (!finance) return;
    downloadCsv(`rapport-finances_${from}_${to}.csv`, [
      [t("reports.from"), from],
      [t("reports.to"), to],
      [t("reports.cashIn"), finance.cash_in],
      [t("reports.cashOut"), finance.cash_out],
      [t("reports.netCash"), finance.net_cash],
      [t("reports.currentOutstanding"), finance.outstanding_balance],
      [t("reports.financeAsOf", { date: finance.as_of }), finance.as_of],
    ]);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-3">
          <Truck className="text-primary hidden size-8 sm:block" aria-hidden="true" />
          <div>
            <h1 className="text-3xl font-bold uppercase">{t("reports.title")}</h1>
            <p className="text-muted-foreground text-sm">{t("reports.description")}</p>
          </div>
        </div>
        {section === "sales" && (
          <Button variant="outline" onClick={exportReport} disabled={!data}>
            <Download className="size-4" /> {t("reports.exportCsv")}
          </Button>
        )}
      </div>

      <div className="panel flex flex-wrap items-end gap-3 p-3">
        <span className="text-muted-foreground basis-full text-sm font-medium">
          {t("reports.periodLabel")}
        </span>
        <label className="grid gap-1 text-xs">
          {t("reports.from")}
          <Input
            type="date"
            value={from}
            max={to}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-xs">
          {t("reports.to")}
          <Input
            type="date"
            value={to}
            min={from}
            max={iso(today)}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        <Button variant="secondary" size="sm" onClick={() => preset(7)}>
          {t("reports.days7")}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => preset(30)}>
          {t("reports.days30")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setTrendPeriod("day");
            setFrom(iso(monthStart));
            setTo(iso(today));
          }}
        >
          {t("reports.thisMonth")}
        </Button>
        <Button variant="secondary" size="sm" onClick={annualPreset}>
          {t("reports.thisYear")}
        </Button>
      </div>
      {section === "sales" && (
        <details className="panel p-3">
          <summary className="cursor-pointer text-sm font-semibold">
            {t("reports.advancedFilters")}
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(
              [
                ["product", "reports.product"],
                ["category", "reports.category"],
                ["customer", "reports.customer"],
                ["seller", "reports.seller"],
                ["location", "reports.location"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="grid gap-1 text-xs">
                {t(label)}
                <Input
                  value={draftFilters[key]}
                  onChange={(event) =>
                    setDraftFilters((current) => ({ ...current, [key]: event.target.value }))
                  }
                />
              </label>
            ))}
            <label className="grid gap-1 text-xs">
              {t("reports.paymentMethod")}
              <select
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                value={draftFilters.paymentMethod}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    paymentMethod: event.target.value,
                  }))
                }
              >
                <option value="">{t("reports.allPaymentMethods")}</option>
                {(["cash", "mobile_money", "bank_transfer", "credit"] as const).map((method) => (
                  <option key={method} value={method}>
                    {t(`reports.paymentMethod.${method}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => setSalesFilters(draftFilters)}>
              {t("reports.applyFilters")}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setDraftFilters(emptySalesFilters);
                setSalesFilters(emptySalesFilters);
              }}
            >
              {t("reports.clearFilters")}
            </Button>
          </div>
        </details>
      )}
      {section === "purchases" && (
        <details className="panel p-3">
          <summary className="cursor-pointer text-sm font-semibold">
            {t("reports.advancedFilters")}
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {(
              [
                ["supplier", "reports.supplier"],
                ["location", "reports.location"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="grid gap-1 text-xs">
                {t(label)}
                <Input
                  value={draftPurchaseFilters[key]}
                  onChange={(event) =>
                    setDraftPurchaseFilters((current) => ({
                      ...current,
                      [key]: event.target.value,
                    }))
                  }
                />
              </label>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => setPurchaseFilters(draftPurchaseFilters)}>
              {t("reports.applyFilters")}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setDraftPurchaseFilters(emptyPurchaseFilters);
                setPurchaseFilters(emptyPurchaseFilters);
              }}
            >
              {t("reports.clearFilters")}
            </Button>
          </div>
        </details>
      )}
      {from > to && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
        >
          {t("reports.invalidRange")}
        </p>
      )}

      <Tabs
        value={section}
        onValueChange={(value) => setSection(value as ReportSection)}
        className="space-y-5"
      >
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:flex sm:w-fit">
          <TabsTrigger value="sales">{t("reports.tabSales")}</TabsTrigger>
          {can("purchases.view") && (
            <TabsTrigger value="purchases">{t("reports.tabPurchases")}</TabsTrigger>
          )}
          {canViewCredits && (
            <>
              <TabsTrigger value="credits">{t("reports.tabCredits")}</TabsTrigger>
            </>
          )}
          {canViewFinance && (
            <>
              <TabsTrigger value="finance">{t("reports.tabFinance")}</TabsTrigger>
            </>
          )}
        </TabsList>

        <TabsContent value="sales" className="space-y-5">
          {reportQuery.isError && (
            <p
              role="alert"
              className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
            >
              {reportQuery.error instanceof Error
                ? reportQuery.error.message
                : t("reports.loadError")}
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((card) => (
              <div key={card.label} className="panel p-4">
                <div className="text-muted-foreground flex items-center gap-2 text-sm">
                  <card.icon className="size-4" aria-hidden="true" />
                  {card.label}
                </div>
                <p className="mt-2 text-2xl font-bold">{card.value}</p>
              </div>
            ))}
          </div>

          <div className="panel p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-bold uppercase">
                {t(trendPeriod === "month" ? "reports.monthlyRevenue" : "reports.dailyRevenue")}
              </h2>
              <div className="text-muted-foreground flex gap-4 text-xs">
                <span>
                  <i className="mr-1 inline-block size-2 rounded-full bg-primary" />
                  {t("reports.revenue")}
                </span>
                <span>
                  <i className="mr-1 inline-block size-2 rounded-full bg-emerald-500" />
                  {t("reports.received")}
                </span>
              </div>
            </div>
            {reportQuery.isLoading ? (
              <p className="text-muted-foreground text-sm">{t("reports.loading")}</p>
            ) : salesTrend.length ? (
              <ul className="divide-border divide-y">
                {salesTrend.map((entry) => (
                  <li
                    key={entry.period}
                    className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
                  >
                    <span className="font-medium">
                      {trendPeriodLabel(entry.period, trendPeriod, language)}
                    </span>
                    <span>
                      {t("reports.sales")}: {money(entry.sales)}
                    </span>
                    <span className="text-muted-foreground">
                      {t("reports.received")}: {money(entry.received)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground py-6 text-center text-sm">
                {t("reports.noSalesPeriod")}
              </p>
            )}
            {data?.summary.total_discount !== undefined && (
              <p className="text-muted-foreground mt-3 text-sm">
                {t("reports.discounts")}:{" "}
                <span className="font-medium text-foreground">
                  {money(data.summary.total_discount)}
                </span>
              </p>
            )}
          </div>

          {data?.summary.profitability && (
            <div
              className={`rounded-md border p-4 text-sm ${
                data.summary.profitability.available
                  ? "border-emerald-500/40 bg-emerald-500/5"
                  : "border-amber-500/40 bg-amber-500/5"
              }`}
            >
              <p className="font-semibold">
                {t(
                  data.summary.profitability.available
                    ? "reports.profitabilityAvailable"
                    : "reports.profitabilityUnavailable",
                )}
              </p>
              {data.summary.profitability.available ? (
                <p className="text-muted-foreground mt-1">
                  {t("reports.totalCost")}: {money(data.summary.total_cost)} ·{" "}
                  {t("reports.grossMargin")}: {money(data.summary.gross_margin)} (
                  {formatNumber(data.summary.gross_margin_percent ?? 0)}%)
                </p>
              ) : (
                <p className="text-muted-foreground mt-1">{data.summary.profitability.reason}</p>
              )}
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="panel p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 className="text-lg font-bold uppercase">{t("reports.topProducts")}</h2>
              </div>
              <ul className="divide-border divide-y">
                {(data?.top_products ?? []).map((product) => (
                  <li
                    key={product.id}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{product.name}</p>
                      <p className="text-muted-foreground text-xs">
                        {product.sku} · {formatNumber(product.quantity_sold)} {t("reports.sold")}
                      </p>
                    </div>
                    <span className="font-semibold">{money(product.revenue)}</span>
                  </li>
                ))}
                {!data?.top_products?.length && (
                  <li className="text-muted-foreground py-6 text-center text-sm">
                    {t("reports.noData")}
                  </li>
                )}
              </ul>
            </div>

            <div className="panel p-4">
              <h2 className="mb-3 text-lg font-bold uppercase">{t("reports.salesBySeller")}</h2>
              <ul className="divide-border divide-y">
                {(data?.sales_by_seller ?? []).map((seller, index) => (
                  <li
                    key={`${seller.seller_id ?? "unassigned"}-${index}`}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {seller.seller_name || t("reports.unassigned")}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {t("reports.saleCount", { count: formatNumber(seller.sale_count) })}
                      </p>
                    </div>
                    <span className="font-semibold">{money(seller.total_sales)}</span>
                  </li>
                ))}
                {!data?.sales_by_seller?.length && (
                  <li className="text-muted-foreground py-6 text-center text-sm">
                    {t("reports.noData")}
                  </li>
                )}
              </ul>
            </div>
          </div>
          <div className="panel p-4">
            <h2 className="mb-3 text-lg font-bold uppercase">{t("reports.salesByLocation")}</h2>
            <ul className="divide-border divide-y">
              {(data?.sales_by_location ?? []).map((location, index) => (
                <li
                  key={`${location.location_id ?? "unassigned"}-${index}`}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      {location.location_name || t("reports.unassignedLocation")}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {t("reports.saleCount", { count: formatNumber(location.sale_count) })}
                    </p>
                  </div>
                  <span className="font-semibold">{money(location.total_sales)}</span>
                </li>
              ))}
              {!data?.sales_by_location?.length && (
                <li className="text-muted-foreground py-5 text-center text-sm">
                  {t("reports.noData")}
                </li>
              )}
            </ul>
          </div>
          <div className="panel p-4">
            <h2 className="mb-3 text-lg font-bold uppercase">
              {t("reports.salesByPaymentMethod")}
            </h2>
            <ul className="divide-border divide-y">
              {(data?.sales_by_payment_method ?? []).map((payment) => (
                <li
                  key={payment.payment_method}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <div>
                    <p className="font-medium">
                      {t(`reports.paymentMethod.${payment.payment_method}`)}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {t("reports.saleCount", { count: formatNumber(payment.sale_count) })}
                    </p>
                  </div>
                  <span className="font-semibold">{money(payment.total_sales)}</span>
                </li>
              ))}
              {!data?.sales_by_payment_method?.length && (
                <li className="text-muted-foreground py-5 text-center text-sm">
                  {t("reports.noData")}
                </li>
              )}
            </ul>
          </div>
          <details className="panel p-4">
            <summary className="cursor-pointer text-lg font-bold uppercase">
              {t("reports.otherSalesAnalyses")}
            </summary>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <section>
                <h2 className="mb-3 font-bold uppercase">{t("reports.salesByStatus")}</h2>
                <ul className="divide-border divide-y">
                  {data?.sales_by_status.map((entry) => (
                    <li key={entry.status} className="flex justify-between gap-3 py-2 text-sm">
                      <span>{t(`reports.saleStatus.${entry.status}`)}</span>
                      <span className="text-right">
                        {formatNumber(entry.sale_count)} · {money(entry.total_sales)}
                      </span>
                    </li>
                  ))}
                  {!data?.sales_by_status.length && (
                    <li className="text-muted-foreground py-4 text-sm">{t("reports.noData")}</li>
                  )}
                </ul>
              </section>
              <section>
                <h2 className="mb-3 font-bold uppercase">{t("reports.topCustomers")}</h2>
                <ul className="divide-border divide-y">
                  {data?.customer_breakdown.map((customer) => (
                    <li
                      key={customer.customer_id}
                      className="flex justify-between gap-3 py-2 text-sm"
                    >
                      <span>{customer.customer__full_name}</span>
                      <span className="font-semibold">{money(customer.total_sales)}</span>
                    </li>
                  ))}
                  {!data?.customer_breakdown.length && (
                    <li className="text-muted-foreground py-4 text-sm">{t("reports.noData")}</li>
                  )}
                </ul>
              </section>
              <section>
                <h2 className="mb-3 font-bold uppercase">{t("reports.inventoryHealth")}</h2>
                <ul className="divide-border divide-y">
                  {[
                    [
                      t("reports.stockUnits"),
                      formatNumber(data?.inventory_status.total_stock_items ?? 0),
                    ],
                    [
                      t("reports.lowStockProducts"),
                      formatNumber(data?.inventory_status.low_stock_products ?? 0),
                    ],
                    [
                      t("reports.healthyStockProducts"),
                      formatNumber(data?.inventory_status.healthy_products ?? 0),
                    ],
                  ].map(([label, value]) => (
                    <li key={label} className="flex justify-between gap-3 py-2 text-sm">
                      <span>{label}</span>
                      <span className="font-semibold">{value}</span>
                    </li>
                  ))}
                </ul>
                {canViewFinance && data?.inventory_status.inventory_value !== undefined && (
                  <div className="mt-3 space-y-2 text-sm">
                    <p>
                      {t("reports.stockValue")}:{" "}
                      <strong>{money(data.inventory_status.inventory_value)}</strong>
                    </p>
                    <p>
                      {t("reports.averageMargin")}:{" "}
                      <strong>
                        {formatNumber(data.inventory_status.average_margin_percent ?? 0)}%
                      </strong>
                    </p>
                    {data.inventory_status.financial_data_quality && (
                      <p className="text-muted-foreground">
                        {t("reports.costCoverage", {
                          covered: formatNumber(
                            data.inventory_status.financial_data_quality.products_with_cost,
                          ),
                          missing: formatNumber(
                            data.inventory_status.financial_data_quality.products_missing_cost,
                          ),
                          percent: formatNumber(
                            data.inventory_status.financial_data_quality.cost_coverage_percent,
                          ),
                        })}
                      </p>
                    )}
                    {!!data.inventory_status.low_margin_products?.length && (
                      <div>
                        <h3 className="font-semibold">{t("reports.lowMarginProducts")}</h3>
                        <ul className="divide-border divide-y">
                          {data.inventory_status.low_margin_products.map((product) => (
                            <li key={product.id} className="flex justify-between gap-3 py-2">
                              <span>
                                {product.name} · {product.sku}
                              </span>
                              <span>{formatNumber(product.margin_percent)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </section>
            </div>
          </details>
        </TabsContent>

        {can("purchases.view") && (
          <TabsContent value="purchases" className="space-y-5">
            <section className="space-y-4" aria-labelledby="purchase-report-title">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="purchase-report-title" className="text-xl font-bold uppercase">
                    {t("reports.purchaseAnalysis")}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t("reports.purchaseAnalysisDescription")}
                  </p>
                </div>
                <Button variant="outline" onClick={exportPurchases} disabled={!purchasesQuery.data}>
                  <Download className="size-4" /> {t("reports.exportCsv")}
                </Button>
              </div>
              {purchasesQuery.isError && (
                <p
                  role="alert"
                  className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
                >
                  {purchasesQuery.error instanceof Error
                    ? purchasesQuery.error.message
                    : t("reports.loadError")}
                </p>
              )}
              {purchasesQuery.isLoading && (
                <p className="text-muted-foreground text-sm">{t("reports.loading")}</p>
              )}
              {purchasesQuery.data && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {[
                      [t("reports.orders"), formatNumber(purchasesQuery.data.summary.order_count)],
                      [
                        t("reports.orderedAmount"),
                        money(purchasesQuery.data.summary.ordered_amount),
                      ],
                      [
                        t("reports.receipts"),
                        formatNumber(purchasesQuery.data.summary.receipt_count),
                      ],
                      [
                        t("reports.acquisitionCosts"),
                        money(purchasesQuery.data.summary.acquisition_costs),
                      ],
                      [
                        t("reports.receivedQuantityLabel"),
                        formatNumber(purchasesQuery.data.summary.received_quantity),
                      ],
                      [
                        t("reports.receivedAmount"),
                        money(purchasesQuery.data.summary.received_amount),
                      ],
                      [
                        t("reports.supplierCount"),
                        formatNumber(purchasesQuery.data.summary.supplier_count),
                      ],
                    ].map(([label, value]) => (
                      <div key={label} className="panel p-4">
                        <p className="text-muted-foreground text-xs tracking-widest uppercase">
                          {label}
                        </p>
                        <p className="mt-2 text-xl font-bold">{value}</p>
                      </div>
                    ))}
                  </div>
                  <p className="text-muted-foreground text-xs">
                    {t("reports.orderedAmountIsNotStock")}
                  </p>
                  <div className="panel p-4">
                    <h3 className="mb-3 font-bold uppercase">{t("reports.suppliersByReceipts")}</h3>
                    <ul className="divide-border divide-y">
                      {purchasesQuery.data.suppliers.map((supplier) => (
                        <li
                          key={supplier.supplier_id}
                          className="flex items-center justify-between gap-3 py-2 text-sm"
                        >
                          <div className="min-w-0">
                            <p className="truncate font-medium">{supplier.supplier}</p>
                            <p className="text-muted-foreground text-xs">
                              {formatNumber(supplier.order_count)}{" "}
                              {t("reports.orders").toLowerCase()}
                              {" · "}
                              {formatNumber(supplier.ordered_quantity)}{" "}
                              {t("reports.quantity").toLowerCase()}
                              {" · "}
                              {money(supplier.ordered_amount)}{" "}
                              {t("reports.orderedAmount").toLowerCase()}
                            </p>
                            <p className="text-muted-foreground text-xs">
                              {formatNumber(supplier.received_quantity)}{" "}
                              {t("reports.receivedQuantityLabel")}
                              {" · "}
                              {formatNumber(supplier.receipt_count)}{" "}
                              {t("reports.receipts").toLowerCase()}
                            </p>
                          </div>
                          <span className="font-semibold">{money(supplier.received_amount)}</span>
                        </li>
                      ))}
                      {!purchasesQuery.data.suppliers.length && (
                        <li className="text-muted-foreground py-5 text-center text-sm">
                          {t("reports.noData")}
                        </li>
                      )}
                    </ul>
                    {purchasesQuery.data.suppliers_truncated && (
                      <p className="text-muted-foreground mt-2 text-xs">
                        {t("reports.suppliersTruncated")}
                      </p>
                    )}
                  </div>
                  {!purchasesQuery.data.data_quality.currency_comparison_available && (
                    <p className="text-muted-foreground text-xs">
                      {t("reports.purchaseCurrencyUnavailable")}
                    </p>
                  )}
                </>
              )}
            </section>
          </TabsContent>
        )}

        {canViewCredits && (
          <TabsContent value="credits" className="space-y-5">
            <section className="space-y-4" aria-labelledby="credit-report-title">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="credit-report-title" className="text-xl font-bold uppercase">
                    {t("reports.creditAnalysis")}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t("reports.creditAnalysisDescription")}
                  </p>
                </div>
                <Button variant="outline" onClick={exportCredits} disabled={!creditsQuery.data}>
                  <Download className="size-4" /> {t("reports.exportCsv")}
                </Button>
              </div>
              {creditsQuery.isError && (
                <p
                  role="alert"
                  className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
                >
                  {creditsQuery.error instanceof Error
                    ? creditsQuery.error.message
                    : t("reports.loadError")}
                </p>
              )}
              {creditsQuery.isLoading && (
                <p className="text-muted-foreground text-sm">{t("reports.loading")}</p>
              )}
              {creditsQuery.data && (
                <>
                  <p className="text-muted-foreground text-xs">
                    {t("reports.currentCreditSnapshot")}
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {[
                      [t("reports.creditTotal"), money(creditSummary.totalCredit)],
                      [t("reports.received"), money(creditSummary.totalPaid)],
                      [t("reports.outstanding"), money(creditSummary.balance)],
                      [t("reports.creditCustomers"), formatNumber(creditSummary.customerCount)],
                    ].map(([label, value]) => (
                      <div key={label} className="panel p-4">
                        <p className="text-muted-foreground text-xs tracking-widest uppercase">
                          {label}
                        </p>
                        <p className="mt-2 text-xl font-bold">{value}</p>
                      </div>
                    ))}
                  </div>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="panel p-4">
                      <h3 className="mb-3 font-bold uppercase">{t("reports.creditAging")}</h3>
                      <ul className="divide-border divide-y">
                        {(["0-30", "31-60", "61-90", "90+"] as const).map((bucket) => (
                          <li
                            key={bucket}
                            className="flex items-center justify-between py-2 text-sm"
                          >
                            <span>{t(`reports.creditAge.${bucket}`)}</span>
                            <span className="font-semibold">
                              {money(creditSummary.aging[bucket])}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="panel p-4">
                      <h3 className="mb-3 font-bold uppercase">
                        {t("reports.largestOpenCredits")}
                      </h3>
                      <ul className="divide-border divide-y">
                        {creditSummary.openCredits.map((customer) => (
                          <li
                            key={customer.customer_id}
                            className="flex items-center justify-between gap-3 py-2 text-sm"
                          >
                            <div className="min-w-0">
                              <p className="truncate font-medium">{customer.customer_name}</p>
                              <p className="text-muted-foreground text-xs">
                                {t(`reports.creditAge.${customer.aging_bucket}`)}
                                {" · "}
                                {t("reports.daysOverdue", {
                                  count: formatNumber(customer.days_overdue),
                                })}
                                {customer.oldest_open_credit_date &&
                                  ` · ${shortDate(customer.oldest_open_credit_date)}`}
                              </p>
                            </div>
                            <span className="font-semibold">{money(customer.balance)}</span>
                          </li>
                        ))}
                        {!creditSummary.openCredits.length && (
                          <li className="text-muted-foreground py-5 text-center text-sm">
                            {t("reports.noOpenCredits")}
                          </li>
                        )}
                      </ul>
                    </div>
                  </div>
                </>
              )}
            </section>
          </TabsContent>
        )}

        {canViewFinance && (
          <TabsContent value="finance" className="space-y-5">
            <section className="space-y-4" aria-labelledby="finance-report-title">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="finance-report-title" className="text-xl font-bold uppercase">
                    {t("reports.financeAnalysis")}
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t("reports.financeAnalysisDescription")}
                    {financeQuery.data &&
                      ` ${t("reports.financeAsOf", { date: financeQuery.data.as_of })}`}
                  </p>
                </div>
                <Button variant="outline" onClick={exportFinance} disabled={!financeQuery.data}>
                  <Download className="size-4" /> {t("reports.exportCsv")}
                </Button>
              </div>
              {financeQuery.isError && (
                <p
                  role="alert"
                  className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
                >
                  {financeQuery.error instanceof Error
                    ? financeQuery.error.message
                    : t("reports.loadError")}
                </p>
              )}
              {financeQuery.isLoading && (
                <p className="text-muted-foreground text-sm">{t("reports.loading")}</p>
              )}
              {financeQuery.data && (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    [t("reports.cashIn"), money(financeQuery.data.cash_in)],
                    [t("reports.cashOut"), money(financeQuery.data.cash_out)],
                    [t("reports.netCash"), money(financeQuery.data.net_cash)],
                    [t("reports.currentOutstanding"), money(financeQuery.data.outstanding_balance)],
                  ].map(([label, value]) => (
                    <div key={label} className="panel p-4">
                      <p className="text-muted-foreground text-xs tracking-widest uppercase">
                        {label}
                      </p>
                      <p className="mt-2 text-xl font-bold">{value}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
