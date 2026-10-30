import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Download, Plus, Save, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { useAuth } from "@/lib/auth";
import { dateTime, formatFileSize, formatNumber, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";
import { statusVariant } from "@/lib/purchase-status";

export const PageRoute = createFileRoute("/_authenticated/commandes/")({
  head: () => ({
    meta: [
      { title: "Commandes fournisseurs — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Gestion des fournisseurs, des reliquats à commander et du réapprovisionnement du magasin.",
      },
      { property: "og:title", content: "Commandes fournisseurs — DJIBEXA" },
      {
        property: "og:description",
        content: "Suivi des commandes fournisseurs et des réceptions de marchandise.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="purchases.view">
      <Commandes />
    </RequirePermission>
  ),
});

type Line = { productId: string; name: string; qty: number; cost: number };
type BackorderRow = {
  productId: string;
  name: string;
  reference: string;
  missing: number;
  cost: number;
};
type ReplenishmentSuggestion = {
  product_id: number;
  name: string;
  reference: string;
  physical_quantity: number;
  alert_threshold: number;
  open_order_quantity: number;
  suggested_quantity: number;
};
type SupplierImport = {
  id: number;
  supplier: number;
  file_name: string;
  status: string;
  parsed_rows: number;
  possible_duplicate_of: number | null;
  rows: {
    id: number;
    reference: string;
    name: string;
    quantity: number;
    unit_price: string;
    currency: string;
    matched_product: string;
    matched_product_id: number | null;
    validation_errors: string[];
    notes: string;
  }[];
  purchase_order: { id: number; reference: string } | null;
};
type SupplierImportRow = SupplierImport["rows"][number];
type ExchangeRateRow = {
  id: number;
  source_currency: string;
  target_currency: string;
  rate: string;
  effective_date: string;
};

function SupplierImportPreviewRow({
  row,
  products,
  t,
  onMatch,
  onCorrect,
  correctionPending,
}: {
  row: SupplierImportRow;
  products: { id: string; name: string; reference: string }[];
  t: (key: string) => string;
  onMatch: (productId: string) => void;
  onCorrect: (values: { quantity: string; unit_price: string; currency: string }) => void;
  correctionPending: boolean;
}) {
  const [draft, setDraft] = useState({
    quantity: String(row.quantity),
    unit_price: row.unit_price,
    currency: row.currency,
  });
  const changed =
    draft.quantity !== String(row.quantity) ||
    draft.unit_price !== row.unit_price ||
    draft.currency !== row.currency;

  return (
    <TableRow>
      <TableCell className="font-mono text-xs">{row.reference || "—"}</TableCell>
      <TableCell>{row.name || "—"}</TableCell>
      <TableCell>
        {row.matched_product ? (
          <span className="text-emerald-700">{row.matched_product}</span>
        ) : (
          <Select value="" onValueChange={onMatch}>
            <SelectTrigger aria-label={t("orders.matchExistingProduct")}>
              <SelectValue placeholder={t("orders.matchExistingProduct")} />
            </SelectTrigger>
            <SelectContent>
              {products.map((product) => (
                <SelectItem key={product.id} value={product.id}>
                  {product.name} ({product.reference})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {row.validation_errors.map((error) => (
          <p key={error} className="text-destructive text-xs">
            {error}
          </p>
        ))}
        {changed && (
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            disabled={correctionPending}
            onClick={() => onCorrect(draft)}
          >
            <Save className="size-3" /> {t("orders.saveCorrection")}
          </Button>
        )}
      </TableCell>
      <TableCell className="text-right">
        <Input
          type="number"
          min={1}
          step={1}
          className="ml-auto w-24"
          aria-label={t("orders.quantity")}
          value={draft.quantity}
          onChange={(event) => setDraft({ ...draft, quantity: event.target.value })}
        />
      </TableCell>
      <TableCell>
        <div className="flex min-w-44 gap-2">
          <Input
            type="number"
            min="0.01"
            step="any"
            aria-label={t("orders.priceCurrency")}
            value={draft.unit_price}
            onChange={(event) => setDraft({ ...draft, unit_price: event.target.value })}
          />
          <Input
            className="w-20 uppercase"
            maxLength={3}
            aria-label={t("orders.currency")}
            value={draft.currency}
            onChange={(event) => setDraft({ ...draft, currency: event.target.value })}
          />
        </div>
      </TableCell>
    </TableRow>
  );
}

function toUiOrderStatus(status: string) {
  if (status === "draft") return "brouillon";
  if (status === "received") return "recue";
  if (status === "cancelled") return "annulee";
  if (status === "approved" || status === "partial_received") return status;
  return "envoyee";
}

function orderStatusLabel(status: string, t: (key: string) => string) {
  const key =
    status === "brouillon" || status === "draft"
      ? "orders.status.draft"
      : status === "recue" || status === "received"
        ? "orders.status.received"
        : status === "annulee" || status === "cancelled"
          ? "orders.status.cancelled"
          : status === "approved"
            ? "orders.status.approved"
            : status === "partial_received"
              ? "orders.status.partial"
              : "orders.status.submitted";
  return t(key);
}

function Commandes() {
  const { t } = useLocale();
  const { can, hasRole } = useAuth();
  const manage = can("purchases.manage");
  const isAdmin = hasRole("admin");
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [supplierOpen, setSupplierOpen] = useState(false);
  const [supplierForm, setSupplierForm] = useState({ name: "", phone: "", address: "" });
  const [importOpen, setImportOpen] = useState(false);
  const [importSupplierId, setImportSupplierId] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<SupplierImport | null>(null);
  const [orderOpen, setOrderOpen] = useState(false);
  const [supplierId, setSupplierId] = useState("");
  const [notes, setNotes] = useState("");
  const [currency, setCurrency] = useState("GNF");
  const [exchangeRate, setExchangeRate] = useState("");
  const [exchangeRateReason, setExchangeRateReason] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [pick, setPick] = useState("");
  const [quickProductOpen, setQuickProductOpen] = useState(false);
  const [quickProductReference, setQuickProductReference] = useState("");
  const [quickProductName, setQuickProductName] = useState("");
  const canCreateProducts = can("products.manage");

  const { data: suppliers } = useQuery({
    queryKey: ["suppliers"],
    queryFn: async () =>
      (await api.list<{ id: number; name: string; phone: string }>("suppliers/")).map(
        (supplier) => ({ ...supplier, id: String(supplier.id) }),
      ),
  });

  const { data: exchangeRates } = useQuery({
    queryKey: ["exchange-rates", "USD", "GNF"],
    queryFn: () =>
      api.list<ExchangeRateRow>("suppliers/exchange-rates/", {
        source_currency: "USD",
        target_currency: "GNF",
      }),
  });
  const today = new Date();
  const todayDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const currentExchangeRate = (exchangeRates ?? []).find(
    (rate) => rate.effective_date <= todayDate,
  );
  const appliedExchangeRate = exchangeRate || currentExchangeRate?.rate || "";
  const hasRateOverride =
    currency === "USD" &&
    Boolean(currentExchangeRate) &&
    Number(appliedExchangeRate) !== Number(currentExchangeRate?.rate);

  const { data: products } = useQuery({
    queryKey: ["products"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          name: string;
          sku: string;
          quantity: number;
          alert_threshold: number;
          purchase_price: string;
        }>("products/")
      ).map((product) => ({
        id: String(product.id),
        name: product.name,
        reference: product.sku,
        stock: product.quantity,
        alert_threshold: product.alert_threshold,
        purchase_price: isAdmin ? Number(product.purchase_price) : 0,
      })),
  });

  const createQuickProduct = useMutation({
    mutationFn: () =>
      api.post<{
        id: number;
        sku: string;
        name: string;
        purchase_price?: string;
      }>("products/", {
        sku: quickProductReference.trim(),
        name: quickProductName.trim(),
        unit: "piece",
        currency: "GNF",
        quantity: 0,
        selling_price: 0,
      }),
    onSuccess: (product) => {
      const productId = String(product.id);
      setLines((previous) => {
        const existing = previous.find((line) => line.productId === productId);
        return existing
          ? previous.map((line) =>
              line.productId === productId ? { ...line, qty: line.qty + 1 } : line,
            )
          : [
              ...previous,
              {
                productId,
                name: product.name,
                qty: 1,
                cost: isAdmin ? Number(product.purchase_price ?? 0) : 0,
              },
            ];
      });
      setQuickProductOpen(false);
      setQuickProductReference("");
      setQuickProductName("");
      void qc.invalidateQueries({ queryKey: ["products"] });
      toast.success(t("products.quickCreateSuccess"));
    },
    onError: (error: Error) =>
      toast.error(t("products.quickCreateError"), { description: error.message }),
  });

  const { data: replenishment } = useQuery({
    queryKey: ["purchase_replenishment_suggestions"],
    queryFn: () =>
      api.get<{ suggestions: ReplenishmentSuggestion[]; limitations: string[] }>(
        "purchase-orders/replenishment-suggestions/",
      ),
  });

  const { data: orders } = useQuery({
    queryKey: ["purchase_orders"],
    queryFn: async () => {
      const [orders, allSuppliers] = await Promise.all([
        api.list<{
          id: number;
          reference: string;
          status: string;
          order_date: string;
          supplier: number;
        }>("purchase-orders/"),
        api.list<{ id: number; name: string }>("suppliers/"),
      ]);
      const supplierNames = new Map(allSuppliers.map((supplier) => [supplier.id, supplier.name]));
      return orders.slice(0, 50).map((order) => ({
        id: String(order.id),
        number: order.reference,
        status: toUiOrderStatus(order.status),
        created_at: order.order_date,
        supplier_name: supplierNames.get(order.supplier) ?? "—",
      }));
    },
  });

  const lowStock = replenishment?.suggestions ?? [];
  const backorders: BackorderRow[] = [];

  const addSupplier = useMutation({
    mutationFn: async () => {
      await api.post("suppliers/", {
        name: supplierForm.name,
        phone: supplierForm.phone,
        address: supplierForm.address,
      });
    },
    onSuccess: () => {
      toast.success(t("orders.supplierAdded"));
      setSupplierOpen(false);
      setSupplierForm({ name: "", phone: "", address: "" });
      void qc.invalidateQueries({ queryKey: ["suppliers"] });
    },
    onError: (e: Error) => toast.error(t("orders.addSupplierError"), { description: e.message }),
  });

  const uploadSupplierImport = useMutation({
    mutationFn: async () => {
      if (!importFile || !importSupplierId) {
        throw new Error(t("orders.chooseSupplierAndFile"));
      }
      const formData = new FormData();
      formData.append("supplier", importSupplierId);
      formData.append("file", importFile);
      return api.post<SupplierImport>("suppliers/imports/", formData);
    },
    onSuccess: (preview) => {
      setImportPreview(preview);
      toast.success(t("orders.importAnalyzed", { count: formatNumber(preview.parsed_rows) }));
    },
    onError: (error: Error) =>
      toast.error(t("orders.analyzeError"), { description: error.message }),
  });

  const confirmSupplierImport = useMutation({
    mutationFn: () => {
      if (!importPreview) throw new Error(t("orders.noImportPreview"));
      return api.post<SupplierImport>(`suppliers/imports/${importPreview.id}/confirm/`, {});
    },
    onSuccess: (result) => {
      setImportOpen(false);
      setImportPreview(null);
      setImportFile(null);
      toast.success(t("orders.importConfirmed"), {
        description: result.purchase_order?.reference,
      });
      void qc.invalidateQueries({ queryKey: ["purchase_orders"] });
      if (result.purchase_order) {
        void navigate({
          to: "/commandes/$orderId",
          params: { orderId: String(result.purchase_order.id) },
        });
      }
    },
    onError: (error: Error) =>
      toast.error(t("orders.confirmError"), { description: error.message }),
  });

  const matchSupplierImportRow = useMutation({
    mutationFn: ({ rowId, productId }: { rowId: number; productId: string }) => {
      if (!importPreview) throw new Error(t("orders.noImportPreview"));
      return api.post<SupplierImport>(
        `suppliers/imports/${importPreview.id}/rows/${rowId}/match/`,
        { product: Number(productId) },
      );
    },
    onSuccess: (preview) => setImportPreview(preview),
    onError: (error: Error) => toast.error(t("orders.matchError"), { description: error.message }),
  });

  const correctSupplierImportRow = useMutation({
    mutationFn: ({
      rowId,
      values,
    }: {
      rowId: number;
      values: { quantity: string; unit_price: string; currency: string };
    }) => {
      if (!importPreview) throw new Error(t("orders.noImportPreview"));
      return api.patch<SupplierImport>(
        `suppliers/imports/${importPreview.id}/rows/${rowId}/correction/`,
        values,
      );
    },
    onSuccess: (preview) => setImportPreview(preview),
    onError: (error: Error) =>
      toast.error(t("orders.correctionError"), { description: error.message }),
  });

  const createOrder = useMutation({
    mutationFn: async () => {
      const order = await api.post<{ id: number; reference: string }>("purchase-orders/", {
        supplier: Number(supplierId),
        reference: `PO-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`,
        notes,
        currency,
        ...(currency === "USD"
          ? {
              exchange_rate: appliedExchangeRate,
              exchange_rate_reason: exchangeRateReason.trim(),
            }
          : {}),
        items: lines.map((line) => ({
          product: Number(line.productId),
          quantity: line.qty,
          ...(isAdmin ? { unit_cost: line.cost } : {}),
        })),
      });
      return { id: String(order.id), number: order.reference };
    },
    onSuccess: (order) => {
      toast.success(t("orders.created", { number: order.number }));
      setOrderOpen(false);
      setLines([]);
      setNotes("");
      setCurrency("GNF");
      setExchangeRate("");
      setExchangeRateReason("");
      void qc.invalidateQueries({ queryKey: ["purchase_orders"] });
      void navigate({ to: "/commandes/$orderId", params: { orderId: order.id } });
    },
    onError: (e: Error) => toast.error(t("orders.createError"), { description: e.message }),
  });

  function addLine(productId: string, qty = 1, cost?: number) {
    const p = (products ?? []).find((x) => x.id === productId);
    if (!p) return;
    setLines((prev) => {
      const found = prev.find((l) => l.productId === productId);
      if (found)
        return prev.map((l) => (l.productId === productId ? { ...l, qty: l.qty + qty } : l));
      return [
        ...prev,
        {
          productId,
          name: p.name,
          qty,
          cost: cost ?? (currency === "GNF" ? Number(p.purchase_price ?? 0) : 0),
        },
      ];
    });
    setOrderOpen(true);
  }

  const total = lines.reduce((s, l) => s + l.qty * l.cost, 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("orders.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("orders.description")}</p>
        </div>
        {manage && (
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <Button
              variant="outline"
              className="w-full sm:w-auto"
              onClick={() => {
                setImportPreview(null);
                setImportOpen(true);
              }}
            >
              <Upload className="size-4" /> {t("orders.importFile")}
            </Button>
            {isAdmin && (
              <Button
                variant="outline"
                className="w-full sm:w-auto"
                onClick={() => setSupplierOpen(true)}
              >
                {t("orders.newSupplier")}
              </Button>
            )}
            <Button className="w-full sm:w-auto" onClick={() => setOrderOpen(true)}>
              {t("orders.newOrder")}
            </Button>
          </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel overflow-x-auto">
          <div className="border-b p-3 text-sm font-semibold uppercase">
            {t("orders.backorders")}
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("orders.product")}</TableHead>
                <TableHead className="text-right">{t("orders.missing")}</TableHead>
                {manage && (
                  <TableHead className="w-44 text-right">{t("orders.addToOrder")}</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {backorders.map((b) => (
                <TableRow key={b.productId}>
                  <TableCell>
                    <p className="font-medium">{b.name}</p>
                    <p className="text-muted-foreground font-mono text-xs">{b.reference}</p>
                  </TableCell>
                  <TableCell className="text-destructive text-right font-semibold">
                    {b.missing}
                  </TableCell>
                  {manage && (
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        className="whitespace-nowrap"
                        aria-label={`${t("orders.addToOrder")} ${b.name}`}
                        onClick={() => addLine(b.productId, b.missing, b.cost)}
                      >
                        <Plus className="size-4" />
                        <span>{t("orders.addToOrder")}</span>
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
              {!backorders?.length && (
                <TableRow>
                  <TableCell
                    colSpan={manage ? 3 : 2}
                    className="text-muted-foreground py-8 text-center"
                  >
                    {t("orders.backordersNone")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <div className="panel overflow-x-auto">
          <div className="border-b p-3 text-sm font-semibold uppercase">
            {t("orders.stockBelowThreshold")}
            <p className="text-muted-foreground mt-1 text-xs font-normal normal-case">
              {t("orders.suggestionBasis")}
            </p>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("orders.product")}</TableHead>
                <TableHead className="text-right">{t("orders.stock")}</TableHead>
                <TableHead className="text-right">{t("orders.suggestedQuantity")}</TableHead>
                {manage && (
                  <TableHead className="w-44 text-right">{t("orders.addToOrder")}</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {lowStock.map((p) => (
                <TableRow key={p.product_id}>
                  <TableCell>
                    <p className="font-medium">{p.name}</p>
                    <p className="text-muted-foreground font-mono text-xs">{p.reference}</p>
                  </TableCell>
                  <TableCell className="text-right font-semibold">{p.physical_quantity}</TableCell>
                  <TableCell className="text-right font-semibold">{p.suggested_quantity}</TableCell>
                  {manage && (
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        className="whitespace-nowrap"
                        aria-label={`${t("orders.addToOrder")} ${p.name}`}
                        onClick={() => addLine(String(p.product_id), p.suggested_quantity)}
                      >
                        <Plus className="size-4" />
                        <span>{t("orders.addToOrder")}</span>
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
              {!lowStock.length && (
                <TableRow>
                  <TableCell
                    colSpan={manage ? 4 : 3}
                    className="text-muted-foreground py-8 text-center"
                  >
                    {t("orders.stockHealthy")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="panel overflow-x-auto">
        <div className="border-b p-3 text-sm font-semibold uppercase">{t("orders.orders")}</div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("orders.number")}</TableHead>
              <TableHead>{t("orders.supplier")}</TableHead>
              <TableHead>{t("orders.status")}</TableHead>
              <TableHead className="hidden text-right sm:table-cell">
                {t("orders.createdAt")}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(orders ?? []).map((o) => (
              <TableRow key={o.id} className="cursor-pointer">
                <TableCell className="font-mono">
                  <Link to="/commandes/$orderId" params={{ orderId: o.id }}>
                    {o.number}
                  </Link>
                </TableCell>
                <TableCell>{o.supplier_name}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant(o.status)}>{orderStatusLabel(o.status, t)}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground hidden text-right text-xs sm:table-cell">
                  {dateTime(o.created_at)}
                </TableCell>
              </TableRow>
            ))}
            {!orders?.length && (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground py-8 text-center">
                  {t("orders.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          setImportOpen(open);
          if (!open) {
            setImportPreview(null);
            setImportFile(null);
          }
        }}
      >
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t(importPreview ? "orders.verifyImport" : "orders.importSupplierFile")}
            </DialogTitle>
          </DialogHeader>
          {!importPreview ? (
            <div className="space-y-4">
              <p className="text-muted-foreground text-sm">
                {t("orders.fileFormats")}. {t("orders.importSafety")}
              </p>
              <div className="space-y-1.5">
                <Label>{t("orders.supplier")}</Label>
                <Select value={importSupplierId} onValueChange={setImportSupplierId}>
                  <SelectTrigger>
                    <SelectValue placeholder={t("orders.chooseSupplier")} />
                  </SelectTrigger>
                  <SelectContent>
                    {(suppliers ?? []).map((supplier) => (
                      <SelectItem key={supplier.id} value={supplier.id}>
                        {supplier.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="supplier-import-file">{t("orders.supplierFile")}</Label>
                <Input
                  id="supplier-import-file"
                  type="file"
                  accept=".csv,.xlsx,.xls,.pdf"
                  onChange={(event) => setImportFile(event.target.files?.[0] ?? null)}
                />
                {importFile && (
                  <p className="text-muted-foreground text-xs">
                    {importFile.name} · {formatFileSize(importFile.size)}
                  </p>
                )}
              </div>
              <DialogFooter>
                <Button
                  disabled={!importSupplierId || !importFile || uploadSupplierImport.isPending}
                  onClick={() => uploadSupplierImport.mutate()}
                >
                  {t("orders.analyzeFile")}
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-sm">
                <div className="flex items-center justify-between gap-3">
                  <p className="min-w-0 truncate font-medium">{importPreview.file_name}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void api
                        .download(
                          `suppliers/imports/${importPreview.id}/document/`,
                          importPreview.file_name,
                        )
                        .catch((error: Error) =>
                          toast.error(t("orders.downloadError"), { description: error.message }),
                        )
                    }
                  >
                    <Download className="size-4" /> {t("orders.downloadOriginal")}
                  </Button>
                </div>
                <p className="text-muted-foreground">
                  {t("orders.linesParsed", { count: formatNumber(importPreview.parsed_rows) })}
                </p>
                {importPreview.possible_duplicate_of && (
                  <p className="text-amber-700">{t("orders.possibleDuplicate")}</p>
                )}
              </div>
              <div className="max-h-[50vh] overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("orders.reference")}</TableHead>
                      <TableHead>{t("orders.designation")}</TableHead>
                      <TableHead>{t("orders.erpMatch")}</TableHead>
                      <TableHead className="text-right">{t("orders.quantity")}</TableHead>
                      <TableHead className="text-right">{t("orders.priceCurrency")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {importPreview.rows.map((row) => (
                      <SupplierImportPreviewRow
                        key={`${importPreview.id}-${row.id}-${row.quantity}-${row.unit_price}-${row.currency}`}
                        row={row}
                        products={products ?? []}
                        t={t}
                        correctionPending={correctSupplierImportRow.isPending}
                        onMatch={(productId) =>
                          matchSupplierImportRow.mutate({ rowId: row.id, productId })
                        }
                        onCorrect={(values) =>
                          correctSupplierImportRow.mutate({ rowId: row.id, values })
                        }
                      />
                    ))}
                    {!importPreview.rows.length && (
                      <TableRow>
                        <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                          {t("orders.fileNoLines")}
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setImportPreview(null)}
                  disabled={confirmSupplierImport.isPending}
                >
                  {t("orders.editFile")}
                </Button>
                <Button
                  disabled={
                    !importPreview.rows.length ||
                    importPreview.rows.some(
                      (row) => !row.matched_product_id || row.validation_errors.length > 0,
                    ) ||
                    confirmSupplierImport.isPending ||
                    matchSupplierImportRow.isPending
                  }
                  onClick={() => confirmSupplierImport.mutate()}
                >
                  {t("orders.confirmImport")}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={supplierOpen} onOpenChange={setSupplierOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("orders.newSupplierTitle")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{t("orders.name")}</Label>
              <Input
                value={supplierForm.name}
                onChange={(e) => setSupplierForm({ ...supplierForm, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("orders.phone")}</Label>
              <Input
                value={supplierForm.phone}
                onChange={(e) => setSupplierForm({ ...supplierForm, phone: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("orders.address")}</Label>
              <Input
                value={supplierForm.address}
                onChange={(e) => setSupplierForm({ ...supplierForm, address: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => addSupplier.mutate()}
              disabled={!supplierForm.name || addSupplier.isPending}
            >
              {t("orders.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={orderOpen} onOpenChange={setOrderOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t("orders.orderSupplierTitle")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{t("orders.supplier")}</Label>
              <Select value={supplierId} onValueChange={setSupplierId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("orders.chooseSupplier")} />
                </SelectTrigger>
                <SelectContent>
                  {(suppliers ?? []).map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>{t("orders.currency")}</Label>
              <Select
                value={currency}
                onValueChange={(nextCurrency) => {
                  setCurrency(nextCurrency);
                  setLines((previous) => previous.map((line) => ({ ...line, cost: 0 })));
                  if (nextCurrency === "GNF") {
                    setExchangeRate("");
                    setExchangeRateReason("");
                  } else if (currentExchangeRate) {
                    setExchangeRate(currentExchangeRate.rate);
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="GNF">GNF</SelectItem>
                  <SelectItem value="USD">USD</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {currency === "USD" && (
              <div className="rounded-md border p-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label>{t("orders.exchangeRateReference")}</Label>
                    <p className="text-sm">
                      {currentExchangeRate
                        ? `${currentExchangeRate.rate} GNF/USD · ${currentExchangeRate.effective_date}`
                        : t("settings.exchangeRateMissing")}
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <Label>{t("orders.exchangeRateApplied")}</Label>
                    <Input
                      type="number"
                      min="0.000001"
                      step="0.000001"
                      value={appliedExchangeRate}
                      readOnly={!isAdmin}
                      onChange={(event) => setExchangeRate(event.target.value)}
                    />
                  </div>
                  {hasRateOverride && (
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label>{t("orders.exchangeRateReason")}</Label>
                      <Input
                        value={exchangeRateReason}
                        onChange={(event) => setExchangeRateReason(event.target.value)}
                      />
                    </div>
                  )}
                </div>
                <p className="text-muted-foreground mt-2 text-xs">
                  {t("orders.exchangeRateOverrideHint")}
                </p>
                {isAdmin && total > 0 && Number(appliedExchangeRate) > 0 && (
                  <p className="mt-2 text-right text-sm font-medium">
                    {t("orders.gnfEquivalent")}: {money(total * Number(appliedExchangeRate))}
                  </p>
                )}
              </div>
            )}

            <div className="space-y-1.5">
              <Label>{t("orders.addProduct")}</Label>
              <Select
                value={pick}
                onValueChange={(v) => {
                  setPick("");
                  addLine(v);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("orders.chooseProduct")} />
                </SelectTrigger>
                <SelectContent>
                  {(products ?? []).map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name} ({p.reference})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {canCreateProducts && (
              <div className="space-y-2 rounded-md border p-3">
                {!quickProductOpen ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setQuickProductOpen(true)}
                  >
                    {t("products.quickCreate")}
                  </Button>
                ) : (
                  <>
                    <p className="text-sm font-medium">{t("products.quickCreateDescription")}</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label>{t("products.internalReference")}</Label>
                        <Input
                          value={quickProductReference}
                          onChange={(event) => setQuickProductReference(event.target.value)}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label>{t("products.name")}</Label>
                        <Input
                          value={quickProductName}
                          onChange={(event) => setQuickProductName(event.target.value)}
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setQuickProductOpen(false)}
                      >
                        {t("common.cancel")}
                      </Button>
                      <Button
                        type="button"
                        disabled={
                          !quickProductReference.trim() ||
                          !quickProductName.trim() ||
                          createQuickProduct.isPending
                        }
                        onClick={() => createQuickProduct.mutate()}
                      >
                        {t("products.quickCreate")}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("orders.designation")}</TableHead>
                    <TableHead className="w-28 text-right">{t("orders.quantity")}</TableHead>
                    {isAdmin && (
                      <TableHead className="w-36 text-right">{t("orders.purchasePrice")}</TableHead>
                    )}
                    <TableHead className="w-36 text-right">{t("orders.total")}</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lines.map((l) => (
                    <TableRow key={l.productId}>
                      <TableCell className="min-w-44 font-medium">{l.name}</TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          min={1}
                          step={1}
                          className="w-24 text-right"
                          aria-label={`${t("orders.quantity")} — ${l.name}`}
                          value={l.qty}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((x) =>
                                x.productId === l.productId
                                  ? { ...x, qty: Math.max(1, Number(e.target.value) || 1) }
                                  : x,
                              ),
                            )
                          }
                        />
                      </TableCell>
                      {isAdmin && (
                        <TableCell>
                          <Input
                            type="number"
                            min={0}
                            step="0.01"
                            aria-label={`${t("orders.purchasePrice")} (${currency}) — ${l.name}`}
                            className="w-32 text-right"
                            value={l.cost}
                            onChange={(e) =>
                              setLines((prev) =>
                                prev.map((x) =>
                                  x.productId === l.productId
                                    ? { ...x, cost: Number(e.target.value) || 0 }
                                    : x,
                                ),
                              )
                            }
                          />
                        </TableCell>
                      )}
                      <TableCell className="text-right font-medium">
                        {money(l.qty * l.cost, currency)}
                      </TableCell>
                      <TableCell>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`${t("common.delete")} ${l.name}`}
                          onClick={() =>
                            setLines((prev) => prev.filter((x) => x.productId !== l.productId))
                          }
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!lines.length && (
                    <TableRow>
                      <TableCell
                        colSpan={isAdmin ? 5 : 4}
                        className="text-muted-foreground py-4 text-center"
                      >
                        {t("orders.linesNone")}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className="space-y-1.5">
              <Label>{t("orders.notes")}</Label>
              <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>

            {isAdmin && (
              <p className="text-right text-sm font-semibold">
                {t("orders.estimatedTotal")} : {money(total, currency)}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              onClick={() => createOrder.mutate()}
              disabled={
                !lines.length ||
                !supplierId ||
                createOrder.isPending ||
                (currency === "USD" && !currentExchangeRate) ||
                (hasRateOverride && !exchangeRateReason.trim())
              }
            >
              {t("orders.createOrder")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
