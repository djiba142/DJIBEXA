import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
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
import { dateTime, formatNumber } from "@/lib/format";
import { useLocale } from "@/lib/locale";

type ReceiptImportPreview = {
  source_name: string;
  source_reference: string;
  supplier_name: string;
  purchase_order: number;
  purchase_order_reference: string;
  supplier_document_reference: string;
  received_date: string;
  currency: string;
  total_rows: number;
  valid_rows: number;
  errors: string[];
  rows: {
    line: number;
    product: number | null;
    product_reference: string;
    product_name: string;
    quantity_ordered: number | null;
    quantity_received: number | null;
    supplier_reference: string;
    location_name: string;
    errors: string[];
  }[];
};

export const PageRoute = createFileRoute("/_authenticated/receptions/")({
  head: () => ({
    meta: [
      { title: "Réceptions fournisseurs — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Réception des marchandises, saisie des frais réels d'approvisionnement et entrée en stock validée.",
      },
      { property: "og:title", content: "Réceptions — DJIBEXA" },
      {
        property: "og:description",
        content: "Coût réel, prix de vente et entrée en stock après validation.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="receptions.view">
      <Receptions />
    </RequirePermission>
  ),
});

function Receptions() {
  const { t } = useLocale();
  const { can } = useAuth();
  const manage = can("receptions.manage");
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [orderId, setOrderId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [warehouseIds, setWarehouseIds] = useState<string[]>([]);
  const [allocations, setAllocations] = useState<Record<string, Record<string, string>>>({});
  const [discrepancyReason, setDiscrepancyReason] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<ReceiptImportPreview | null>(null);

  const { data: receptions } = useQuery({
    queryKey: ["receptions"],
    queryFn: async () => {
      const [receipts, orders, locations] = await Promise.all([
        api.list<{
          id: number;
          reference: string;
          purchase_order: number;
          location: number | null;
          status: string;
          created_at: string;
          received_date: string;
        }>("purchases/receipts/"),
        api.list<{ id: number; reference: string; supplier: number; supplier_name: string }>(
          "purchases/orders/",
        ),
        api.list<{ id: number; name: string }>("inventory/locations/"),
      ]);
      return receipts.map((receipt) => {
        const order = orders.find((item) => item.id === receipt.purchase_order);
        return {
          id: String(receipt.id),
          number: receipt.reference,
          status: receipt.status,
          created_at: receipt.created_at,
          validated_at: receipt.status === "received" ? receipt.received_date : null,
          suppliers: {
            name: order?.supplier_name ?? "—",
          },
          warehouses: {
            name: locations.find((location) => location.id === receipt.location)?.name ?? "—",
          },
        };
      });
    },
  });

  const { data: orders } = useQuery({
    queryKey: ["purchase_orders", "receivable"],
    queryFn: async () => {
      const purchaseOrders = await api.list<{
        id: number;
        reference: string;
        supplier: number;
        supplier_name: string;
        status: string;
        items: { product: number; quantity: number; unit_cost?: string }[];
      }>("purchases/orders/");
      return purchaseOrders
        .filter((order) => !["received", "cancelled"].includes(order.status))
        .map((order) => ({
          ...order,
          id: String(order.id),
          number: order.reference,
          supplier_id: order.supplier,
          suppliers: { name: order.supplier_name },
        }));
    },
  });

  const { data: warehouses } = useQuery({
    queryKey: ["warehouses"],
    queryFn: () => api.list<{ id: number; name: string }>("inventory/locations/"),
  });

  const { data: products } = useQuery({
    queryKey: ["products"],
    queryFn: () => api.list<{ id: number; name: string; sku: string }>("products/"),
  });

  const create = useMutation({
    mutationFn: async () => {
      const order = (orders ?? []).find((o) => o.id === orderId);
      if (!order) throw new Error(t("receipts.chooseOrderError"));
      if (!discrepancyReason.trim()) {
        throw new Error(t("receipts.deliveryReasonRequired"));
      }
      const timestamp = Date.now();
      const receipts = warehouseIds.flatMap((locationId, index) => {
        const items = order.items.flatMap((item) => {
          const quantity = Number(allocations[String(item.product)]?.[locationId] ?? 0);
          return quantity > 0
            ? [
                {
                  product: item.product,
                  quantity_received: quantity,
                  ...(item.unit_cost ? { unit_cost: item.unit_cost } : {}),
                },
              ]
            : [];
        });
        return items.length
          ? [
              {
                purchase_order: Number(order.id),
                location: Number(locationId),
                reference: `REC-${timestamp}-${index + 1}`,
                allocation_method: "value",
                discrepancy_reason: discrepancyReason.trim(),
                items,
              },
            ]
          : [];
      });
      if (!receipts.length) throw new Error(t("receipts.enterReceivedQuantity"));
      const created = await api.post<{ id: number }[]>("purchases/receipts/batch/", { receipts });
      return created.map((receipt) => String(receipt.id));
    },
    onSuccess: (ids) => {
      setOpen(false);
      setOrderId("");
      setWarehouseIds([]);
      setAllocations({});
      setDiscrepancyReason("");
      void qc.invalidateQueries({ queryKey: ["receptions"] });
      toast.success(t("receipts.batchDraftCreated", { count: ids.length }));
      void navigate({ to: "/receptions/$receptionId", params: { receptionId: ids[0] } });
    },
    onError: (e: Error) => toast.error(t("receipts.createError"), { description: e.message }),
  });

  const previewReceiptImport = useMutation({
    mutationFn: () => {
      if (!importFile || !orderId) throw new Error(t("receipts.importChooseFileAndOrder"));
      const formData = new FormData();
      formData.append("file", importFile);
      formData.append("purchase_order", orderId);
      if (warehouseIds[0]) formData.append("location", warehouseIds[0]);
      formData.append("action", "preview");
      return api.post<ReceiptImportPreview>("purchases/receipts/import/", formData);
    },
    onSuccess: setImportPreview,
    onError: (error: Error) =>
      toast.error(t("receipts.importError"), { description: error.message }),
  });

  const confirmReceiptImport = useMutation({
    mutationFn: async () => {
      if (!importFile || !orderId || !importPreview) {
        throw new Error(t("receipts.importAnalyzeFirst"));
      }
      const formData = new FormData();
      formData.append("file", importFile);
      formData.append("purchase_order", orderId);
      if (warehouseIds[0]) formData.append("location", warehouseIds[0]);
      formData.append("action", "confirm");
      formData.append("discrepancy_reason", discrepancyReason.trim());
      return api.post<{ id: number; reference: string }[]>("purchases/receipts/import/", formData);
    },
    onSuccess: (created) => {
      setOpen(false);
      setOrderId("");
      setWarehouseIds([]);
      setAllocations({});
      setDiscrepancyReason("");
      setImportFile(null);
      setImportPreview(null);
      void qc.invalidateQueries({ queryKey: ["receptions"] });
      toast.success(t("receipts.importCreated", { count: created.length }));
      if (created[0]) {
        void navigate({
          to: "/receptions/$receptionId",
          params: { receptionId: String(created[0].id) },
        });
      }
    },
    onError: (error: Error) =>
      toast.error(t("receipts.importError"), { description: error.message }),
  });

  const selectedOrder = (orders ?? []).find((order) => order.id === orderId);
  const overAllocated = (selectedOrder?.items ?? []).some((item) => {
    const allocated = warehouseIds.reduce(
      (sum, locationId) => sum + Number(allocations[String(item.product)]?.[locationId] ?? 0),
      0,
    );
    return allocated > item.quantity;
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("receipts.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("receipts.description")}</p>
        </div>
        {manage && <Button onClick={() => setOpen(true)}>{t("receipts.new")}</Button>}
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("receipts.number")}</TableHead>
              <TableHead>{t("receipts.supplier")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("receipts.destination")}</TableHead>
              <TableHead>{t("receipts.status")}</TableHead>
              <TableHead className="text-right">{t("receipts.date")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(receptions ?? []).map((r) => (
              <TableRow key={r.id} className="cursor-pointer">
                <TableCell className="font-mono text-xs">
                  <Link to="/receptions/$receptionId" params={{ receptionId: r.id }}>
                    {r.number}
                  </Link>
                </TableCell>
                <TableCell>{r.suppliers?.name ?? "—"}</TableCell>
                <TableCell className="hidden sm:table-cell">{r.warehouses?.name ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant={r.status === "received" ? "default" : "secondary"}>
                    {r.status === "received" ? t("receipts.validated") : t("receipts.draft")}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground text-right text-xs">
                  {dateTime(r.validated_at ?? r.created_at)}
                </TableCell>
              </TableRow>
            ))}
            {!receptions?.length && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-10 text-center">
                  {t("receipts.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          setOpen(nextOpen);
          if (!nextOpen) {
            setOrderId("");
            setWarehouseIds([]);
            setAllocations({});
            setDiscrepancyReason("");
            setImportFile(null);
            setImportPreview(null);
          }
        }}
      >
        <DialogContent className="max-h-[90vh] max-w-6xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("receipts.new")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{t("receipts.order")}</Label>
              <Select
                value={orderId}
                onValueChange={(value) => {
                  setOrderId(value);
                  setAllocations({});
                  setImportPreview(null);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("receipts.chooseOrder")} />
                </SelectTrigger>
                <SelectContent>
                  {(orders ?? []).map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.number} — {o.suppliers?.name || t("receipts.noSupplier")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("receipts.storageLocation")}</Label>
              <Select value={warehouseId} onValueChange={setWarehouseId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("receipts.chooseLocation")} />
                </SelectTrigger>
                <SelectContent>
                  {(warehouses ?? []).map((w) => (
                    <SelectItem key={w.id} value={String(w.id)}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                variant="outline"
                disabled={!warehouseId || warehouseIds.includes(warehouseId)}
                onClick={() => {
                  if (warehouseId && !warehouseIds.includes(warehouseId)) {
                    setWarehouseIds((previous) => [...previous, warehouseId]);
                    setImportPreview(null);
                  }
                }}
              >
                {t("receipts.addWarehouse")}
              </Button>
            </div>
            {warehouseIds.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {warehouseIds.map((locationId) => (
                  <Button
                    key={locationId}
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      setWarehouseIds((previous) => previous.filter((id) => id !== locationId))
                    }
                  >
                    {warehouses?.find((location) => String(location.id) === locationId)?.name ??
                      locationId}
                    <span className="ml-2">×</span>
                  </Button>
                ))}
              </div>
            )}
            {selectedOrder && warehouseIds.length > 0 && (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Produit / référence</TableHead>
                      <TableHead className="text-right">{t("receipts.ordered")}</TableHead>
                      {warehouseIds.map((locationId) => (
                        <TableHead key={locationId} className="min-w-32 text-right">
                          {warehouses?.find((location) => String(location.id) === locationId)?.name}
                        </TableHead>
                      ))}
                      <TableHead className="text-right">{t("receipts.unallocated")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedOrder.items.map((item) => {
                      const allocated = warehouseIds.reduce(
                        (sum, locationId) =>
                          sum + Number(allocations[String(item.product)]?.[locationId] ?? 0),
                        0,
                      );
                      const product = products?.find((candidate) => candidate.id === item.product);
                      return (
                        <TableRow key={item.product}>
                          <TableCell>
                            <div className="font-medium">
                              {product?.name ?? `Produit ${item.product}`}
                            </div>
                            <div className="text-muted-foreground font-mono text-xs">
                              {product?.sku ?? ""}
                            </div>
                          </TableCell>
                          <TableCell className="text-right">{item.quantity}</TableCell>
                          {warehouseIds.map((locationId) => (
                            <TableCell key={locationId}>
                              <Input
                                type="number"
                                min={0}
                                max={item.quantity}
                                step={1}
                                className="w-24 text-right"
                                aria-label={`${product?.name ?? item.product} — ${warehouses?.find((location) => String(location.id) === locationId)?.name}`}
                                value={allocations[String(item.product)]?.[locationId] ?? ""}
                                onChange={(event) => {
                                  const rawValue = event.target.value;
                                  const value =
                                    rawValue === ""
                                      ? ""
                                      : String(Math.max(0, Math.floor(Number(rawValue) || 0)));
                                  setAllocations((previous) => ({
                                    ...previous,
                                    [String(item.product)]: {
                                      ...previous[String(item.product)],
                                      [locationId]: value,
                                    },
                                  }));
                                }}
                              />
                            </TableCell>
                          ))}
                          <TableCell
                            className={`text-right ${allocated > item.quantity ? "text-destructive" : ""}`}
                          >
                            {item.quantity - allocated}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
                <p className="text-muted-foreground p-3 text-sm">{t("receipts.unallocatedHint")}</p>
              </div>
            )}
            {selectedOrder && warehouseIds.length > 0 && (
              <div className="space-y-1.5">
                <Label>{t("receipts.deliveryReferenceReason")}</Label>
                <Input
                  value={discrepancyReason}
                  onChange={(event) => setDiscrepancyReason(event.target.value)}
                  placeholder={t("receipts.deliveryReferencePlaceholder")}
                />
              </div>
            )}
            <div className="space-y-3 rounded-md border p-4">
              <div>
                <h3 className="font-semibold">{t("receipts.importTitle")}</h3>
                <p className="text-muted-foreground text-sm">{t("receipts.importDescription")}</p>
              </div>
              <Input
                type="file"
                accept=".xlsx,.csv"
                aria-label={t("receipts.importFile")}
                onChange={(event) => {
                  setImportFile(event.target.files?.[0] ?? null);
                  setImportPreview(null);
                }}
              />
              <Button
                type="button"
                variant="outline"
                disabled={!importFile || !selectedOrder || previewReceiptImport.isPending}
                onClick={() => previewReceiptImport.mutate()}
              >
                {previewReceiptImport.isPending
                  ? t("receipts.importAnalyzing")
                  : t("receipts.importAnalyze")}
              </Button>
              {importPreview && (
                <div className="space-y-3">
                  <div className="text-sm">
                    <p className="font-medium">
                      {importPreview.source_name} — {importPreview.supplier_name}
                    </p>
                    <p className="text-muted-foreground">
                      {t("receipts.importSummary", {
                        valid: formatNumber(importPreview.valid_rows),
                        total: formatNumber(importPreview.total_rows),
                      })}
                      {importPreview.supplier_document_reference
                        ? ` · ${importPreview.supplier_document_reference}`
                        : ""}
                    </p>
                  </div>
                  <div className="max-h-60 overflow-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t("receipts.importProduct")}</TableHead>
                          <TableHead>{t("receipts.ordered")}</TableHead>
                          <TableHead>{t("receipts.quantityReceived")}</TableHead>
                          <TableHead>{t("receipts.storageLocation")}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {importPreview.rows.map((row) => (
                          <TableRow key={row.line}>
                            <TableCell>
                              <div>{row.product_name || t("receipts.importUnknownProduct")}</div>
                              <div className="text-muted-foreground font-mono text-xs">
                                {row.product_reference}
                                {row.supplier_reference ? ` · ${row.supplier_reference}` : ""}
                              </div>
                              {row.errors.map((error) => (
                                <p key={error} className="text-destructive text-xs">
                                  {error}
                                </p>
                              ))}
                            </TableCell>
                            <TableCell>{row.quantity_ordered ?? "—"}</TableCell>
                            <TableCell>{row.quantity_received ?? "—"}</TableCell>
                            <TableCell>{row.location_name || "—"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  {importPreview.errors.map((error) => (
                    <p key={error} className="text-destructive text-sm">
                      {error}
                    </p>
                  ))}
                  <Button
                    type="button"
                    disabled={
                      importPreview.errors.length > 0 ||
                      importPreview.valid_rows === 0 ||
                      confirmReceiptImport.isPending ||
                      !discrepancyReason.trim()
                    }
                    onClick={() => confirmReceiptImport.mutate()}
                  >
                    {confirmReceiptImport.isPending
                      ? t("receipts.importCreating")
                      : t("receipts.importCreateDraft")}
                  </Button>
                  <p className="text-muted-foreground text-xs">
                    {t("receipts.importStockNotChanged")}
                  </p>
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => create.mutate()}
              disabled={
                !selectedOrder ||
                warehouseIds.length === 0 ||
                overAllocated ||
                !discrepancyReason.trim() ||
                create.isPending
              }
            >
              {t("receipts.batchDraftsCreate")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
