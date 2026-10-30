import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Download, Package, RotateCcw, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { RequirePermission } from "@/components/RequirePermission";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/rapports-inventaire")({
  head: () => ({
    meta: [
      { title: "Rapports de stock et rotation — DJIBEXA" },
      {
        name: "description",
        content: "Stocks autorisés, ventes observées, rotations et signaux de réapprovisionnement.",
      },
      { property: "og:title", content: "Rapports de stock — DJIBEXA" },
      {
        property: "og:description",
        content: "Consultez la disponibilité, la rotation et les seuils de réapprovisionnement.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="inventory.view">
      <RapportInventaire />
    </RequirePermission>
  ),
});

type Period = "jour" | "mois" | "trimestre" | "annee";
type StockProduct = {
  product_id: number;
  name: string;
  sku: string;
  quantity: number;
  alert_threshold: number;
  locations: { location_id: number; location: string; quantity: number }[];
};
type RotationProduct = {
  product_id: number;
  name: string;
  sku: string;
  quantity_on_hand: number;
  quantity_sold: number;
  average_daily_sales: number;
  days_of_stock: number | null;
  rotation_status: "fast" | "slow" | "dormant";
  reorder_signal: boolean;
};
type InventoryReport = {
  summary: {
    total_stock_units: number;
    tracked_products: number;
    low_stock_products: number;
    out_of_stock_products: number;
    untracked_products_in_scope: number;
  };
  stock_by_location: {
    location_id: number;
    location: string;
    total_units: number;
    products: number;
  }[];
  inventory: StockProduct[];
  inventory_truncated: boolean;
  low_stock: StockProduct[];
  low_stock_truncated: boolean;
  rotation: {
    period_start: string;
    period_end: string;
    period_days: number;
    fast_moving_threshold_units_per_day: number;
    low_cover_threshold_days: number;
    returns_separately_tracked: boolean;
    products: RotationProduct[];
    truncated: boolean;
  };
  movement_summary: Record<string, { count: number; quantity: number }>;
  inventory_scope: {
    source: string;
    location_filter_applied: boolean;
    costs_included: boolean;
  };
};

const PERIODS: Period[] = ["jour", "mois", "trimestre", "annee"];
const PERIOD_TRANSLATION: Record<Period, string> = {
  jour: "inventoryReport.periodDaily",
  mois: "inventoryReport.periodMonthly",
  trimestre: "inventoryReport.periodQuarterly",
  annee: "inventoryReport.periodYearly",
};

function dateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function periodRange(period: Period, reference: string) {
  const date = new Date(`${reference}T00:00:00`);
  if (period === "jour") {
    return {
      start: date,
      end: new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1),
    };
  }
  if (period === "mois") {
    return {
      start: new Date(date.getFullYear(), date.getMonth(), 1),
      end: new Date(date.getFullYear(), date.getMonth() + 1, 1),
    };
  }
  if (period === "trimestre") {
    const quarterMonth = Math.floor(date.getMonth() / 3) * 3;
    return {
      start: new Date(date.getFullYear(), quarterMonth, 1),
      end: new Date(date.getFullYear(), quarterMonth + 3, 1),
    };
  }
  return {
    start: new Date(date.getFullYear(), 0, 1),
    end: new Date(date.getFullYear() + 1, 0, 1),
  };
}

function exportCsv(filename: string, report: InventoryReport, t: (key: string) => string) {
  const rows: (string | number)[][] = [
    [
      t("inventoryReport.merchandise"),
      t("reports.reference"),
      t("inventoryReport.quantityInStock"),
      t("inventoryReport.warehouse"),
      t("inventoryReport.rotation"),
      t("inventoryReport.soldDuringPeriod"),
      t("inventoryReport.daysOfStock"),
      t("inventoryReport.reorderSignal"),
    ],
    ...report.rotation.products.map((product) => {
      const stock = report.inventory.find((item) => item.product_id === product.product_id);
      return [
        product.name,
        product.sku,
        product.quantity_on_hand,
        stock?.locations.map((location) => location.location).join(", ") ?? "",
        t(`inventoryReport.rotation.${product.rotation_status}`),
        product.quantity_sold,
        product.days_of_stock ?? "",
        product.reorder_signal ? t("inventoryReport.yes") : t("inventoryReport.no"),
      ];
    }),
    [],
    [
      t("inventoryReport.lowStockItems"),
      t("reports.reference"),
      t("inventoryReport.quantityInStock"),
      t("inventoryReport.lowStockThreshold"),
      t("inventoryReport.warehouse"),
    ],
    ...report.low_stock.map((product) => [
      product.name,
      product.sku,
      product.quantity,
      product.alert_threshold,
      product.locations.map((location) => location.location).join(", "),
    ]),
  ];
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(";"))
    .join("\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function RapportInventaire() {
  const { t, language } = useLocale();
  const [period, setPeriod] = useState<Period>("mois");
  const [referenceDate, setReferenceDate] = useState(() => dateInputValue(new Date()));
  const [warehouse, setWarehouse] = useState("all");
  const [sortBy, setSortBy] = useState<"rotation" | "quantity">("rotation");
  const [draftSearch, setDraftSearch] = useState({ product: "", category: "" });
  const [reportSearch, setReportSearch] = useState({ product: "", category: "" });
  const { start, end } = periodRange(period, referenceDate);
  const endDate = new Date(end.getTime() - 1);
  const startDateValue = dateInputValue(start);
  const endDateValue = dateInputValue(endDate);

  const warehousesQuery = useQuery({
    queryKey: ["warehouses-list"],
    queryFn: () => api.list<{ id: number; name: string }>("inventory/locations/"),
  });
  const reportQuery = useQuery({
    queryKey: ["inventory-bi-report", startDateValue, endDateValue, warehouse, reportSearch],
    queryFn: () =>
      api.get<InventoryReport>("reports/inventory/", {
        start_date: startDateValue,
        end_date: endDateValue,
        location: warehouse === "all" ? undefined : warehouse,
        product_search: reportSearch.product || undefined,
        category_search: reportSearch.category || undefined,
      }),
  });
  const report = reportQuery.data;
  const rows = useMemo(() => {
    const rotationByProduct = new Map(
      (report?.rotation.products ?? []).map((product) => [product.product_id, product]),
    );
    return [...(report?.inventory ?? [])]
      .map((product) => ({
        ...product,
        rotation: rotationByProduct.get(product.product_id),
      }))
      .sort((left, right) =>
        sortBy === "quantity"
          ? right.quantity - left.quantity
          : (right.rotation?.average_daily_sales ?? 0) - (left.rotation?.average_daily_sales ?? 0),
      );
  }, [report?.inventory, report?.rotation.products, sortBy]);

  const cards = [
    {
      label: t("inventoryReport.quantityInStock"),
      value: formatNumber(report?.summary.total_stock_units ?? 0),
      icon: Package,
    },
    {
      label: t("inventoryReport.trackedProducts"),
      value: formatNumber(report?.summary.tracked_products ?? 0),
      icon: RotateCcw,
    },
    {
      label: t("inventoryReport.lowStock"),
      value: formatNumber(report?.summary.low_stock_products ?? 0),
      icon: TriangleAlert,
    },
    {
      label: t("inventoryReport.outOfStock"),
      value: formatNumber(report?.summary.out_of_stock_products ?? 0),
      icon: TriangleAlert,
    },
  ];

  const movementLabels: Record<string, string> = {
    in: t("inventoryReport.stockIn"),
    out: t("inventoryReport.stockOut"),
    adjustment: t("inventoryReport.adjustments"),
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("inventoryReport.title")}</h1>
          <p className="text-muted-foreground text-sm">
            {t(PERIOD_TRANSLATION[period])} ·{" "}
            {t("inventoryReport.dateRange", {
              from: start.toLocaleDateString(language),
              to: endDate.toLocaleDateString(language),
            })}
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() =>
            report && exportCsv(`rotation-stock-${startDateValue}-${endDateValue}.csv`, report, t)
          }
          disabled={!report}
        >
          <Download className="size-4" /> {t("reports.exportCsv")}
        </Button>
      </div>

      <details className="panel p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t("inventoryReport.filters")}
        </summary>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Select value={period} onValueChange={(value) => setPeriod(value as Period)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIODS.map((item) => (
                <SelectItem key={item} value={item}>
                  {t(PERIOD_TRANSLATION[item])}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="date"
            className="w-44"
            value={referenceDate}
            onChange={(event) => setReferenceDate(event.target.value)}
          />
          <Select value={warehouse} onValueChange={setWarehouse}>
            <SelectTrigger className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("inventoryReport.allWarehouses")}</SelectItem>
              {(warehousesQuery.data ?? []).map((item) => (
                <SelectItem key={item.id} value={String(item.id)}>
                  {item.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sortBy} onValueChange={(value) => setSortBy(value as typeof sortBy)}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="rotation">{t("inventoryReport.sortByRotation")}</SelectItem>
              <SelectItem value="quantity">{t("inventoryReport.sortByQuantity")}</SelectItem>
            </SelectContent>
          </Select>
          <label className="grid gap-1 text-xs">
            {t("reports.product")}
            <Input
              value={draftSearch.product}
              onChange={(event) =>
                setDraftSearch((current) => ({ ...current, product: event.target.value }))
              }
            />
          </label>
          <label className="grid gap-1 text-xs">
            {t("reports.category")}
            <Input
              value={draftSearch.category}
              onChange={(event) =>
                setDraftSearch((current) => ({ ...current, category: event.target.value }))
              }
            />
          </label>
          <Button size="sm" onClick={() => setReportSearch(draftSearch)}>
            {t("reports.applyFilters")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setDraftSearch({ product: "", category: "" });
              setReportSearch({ product: "", category: "" });
            }}
          >
            {t("reports.clearFilters")}
          </Button>
        </div>
      </details>

      {reportQuery.isError && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 p-3 text-sm text-destructive"
        >
          {reportQuery.error instanceof Error
            ? reportQuery.error.message
            : t("inventoryReport.loadError")}
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <div key={card.label} className="panel p-4">
            <p className="text-muted-foreground flex items-center gap-2 text-xs tracking-widest uppercase">
              <card.icon className="size-4" aria-hidden="true" />
              {card.label}
            </p>
            <p className="mt-2 text-xl font-bold">{card.value}</p>
          </div>
        ))}
      </div>

      <div className="panel p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold uppercase">{t("inventoryReport.lowStockItems")}</h2>
          {report?.low_stock_truncated && (
            <span className="text-muted-foreground text-xs">
              {t("inventoryReport.lowStockTruncated")}
            </span>
          )}
        </div>
        <ul className="divide-border divide-y">
          {(report?.low_stock ?? []).map((product) => (
            <li
              key={product.product_id}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
            >
              <div>
                <p className="font-medium">{product.name}</p>
                <p className="text-muted-foreground text-xs">{product.sku}</p>
              </div>
              <span className="font-semibold">
                {formatNumber(product.quantity)} / {formatNumber(product.alert_threshold)}
              </span>
            </li>
          ))}
          {!report?.low_stock.length && (
            <li className="text-muted-foreground py-4 text-sm">
              {t("inventoryReport.noLowStock")}
            </li>
          )}
        </ul>
      </div>

      <details className="panel p-4">
        <summary className="cursor-pointer text-sm font-medium">
          {t("inventoryReport.byWarehouse")} · {t("inventoryReport.movementSummary")}
        </summary>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <h2 className="mb-3 text-lg font-bold uppercase">{t("inventoryReport.byWarehouse")}</h2>
            <ul className="divide-border divide-y">
              {(report?.stock_by_location ?? []).map((location) => (
                <li
                  key={location.location_id}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <span className="font-medium">{location.location}</span>
                  <span className="text-muted-foreground">
                    {formatNumber(location.total_units)} {t("inventoryReport.items")}
                    {" · "}
                    {formatNumber(location.products)} {t("inventoryReport.trackedProducts")}
                  </span>
                </li>
              ))}
              {!report?.stock_by_location.length && (
                <li className="text-muted-foreground py-5 text-center text-sm">
                  {t("inventoryReport.empty")}
                </li>
              )}
            </ul>
          </div>
          <div>
            <h2 className="mb-3 text-lg font-bold uppercase">
              {t("inventoryReport.movementSummary")}
            </h2>
            <div className="grid gap-2 sm:grid-cols-3">
              {Object.entries(report?.movement_summary ?? {}).map(([key, movement]) => (
                <div key={key} className="rounded-md border p-3">
                  <p className="text-muted-foreground text-xs uppercase">
                    {movementLabels[key] ?? key}
                  </p>
                  <p className="mt-1 font-semibold">{formatNumber(movement.quantity)}</p>
                  <p className="text-muted-foreground text-xs">
                    {t("inventoryReport.movementCount", { count: formatNumber(movement.count) })}
                  </p>
                </div>
              ))}
              {!Object.keys(report?.movement_summary ?? {}).length && (
                <p className="text-muted-foreground py-5 text-sm">
                  {t("inventoryReport.noMovements")}
                </p>
              )}
            </div>
          </div>
        </div>
      </details>

      <div className="panel overflow-x-auto">
        <div className="flex flex-wrap items-center justify-between gap-2 p-4">
          <div>
            <h2 className="text-lg font-bold uppercase">{t("inventoryReport.rotation")}</h2>
            <p className="text-muted-foreground text-xs">
              {t("inventoryReport.rotationMethod", {
                days: report?.rotation.period_days ?? 0,
                threshold: report?.rotation.low_cover_threshold_days ?? 7,
              })}
            </p>
          </div>
          {report?.rotation.truncated && (
            <span className="text-muted-foreground text-xs">{t("inventoryReport.truncated")}</span>
          )}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventoryReport.merchandise")}</TableHead>
              <TableHead>{t("inventoryReport.warehouse")}</TableHead>
              <TableHead className="text-right">{t("inventoryReport.quantityInStock")}</TableHead>
              <TableHead className="text-right">{t("inventoryReport.soldDuringPeriod")}</TableHead>
              <TableHead className="text-right">{t("inventoryReport.daysOfStock")}</TableHead>
              <TableHead>{t("inventoryReport.rotation")}</TableHead>
              <TableHead>{t("inventoryReport.reorderSignal")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reportQuery.isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="text-muted-foreground py-8 text-center">
                  {t("reports.loading")}
                </TableCell>
              </TableRow>
            )}
            {rows.map((product) => (
              <TableRow key={product.product_id}>
                <TableCell>
                  <p className="font-medium">{product.name}</p>
                  <p className="text-muted-foreground font-mono text-xs">{product.sku}</p>
                </TableCell>
                <TableCell className="min-w-40">
                  {product.locations.map((location) => (
                    <p key={location.location_id} className="text-sm">
                      {location.location} · {formatNumber(location.quantity)}
                    </p>
                  ))}
                  {!product.locations.length && "—"}
                </TableCell>
                <TableCell className="text-right font-semibold">
                  {formatNumber(product.quantity)}
                </TableCell>
                <TableCell className="text-right">
                  {formatNumber(product.rotation?.quantity_sold ?? 0)}
                </TableCell>
                <TableCell className="text-right">
                  {product.rotation?.days_of_stock == null
                    ? "—"
                    : formatNumber(product.rotation.days_of_stock)}
                </TableCell>
                <TableCell>
                  {product.rotation
                    ? t(`inventoryReport.rotation.${product.rotation.rotation_status}`)
                    : "—"}
                </TableCell>
                <TableCell>
                  {product.rotation?.reorder_signal ? (
                    <span className="text-amber-700 dark:text-amber-400">
                      {t("inventoryReport.reorderRequired")}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">{t("inventoryReport.noReorder")}</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!reportQuery.isLoading && !rows.length && (
              <TableRow>
                <TableCell colSpan={7} className="text-muted-foreground py-8 text-center">
                  {t("inventoryReport.empty")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {report && (
        <p className="text-muted-foreground text-xs">
          {t("inventoryReport.qualityNote", {
            count: formatNumber(report.summary.untracked_products_in_scope),
          })}
          {report.rotation.returns_separately_tracked
            ? ""
            : ` ${t("inventoryReport.returnsNotSeparated")}`}
        </p>
      )}
    </div>
  );
}
