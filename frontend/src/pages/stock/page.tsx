import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { FileUp, History, PackagePlus, PencilLine } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { RequirePermission } from "@/components/RequirePermission";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { dateTime, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const Route = createFileRoute("/_authenticated/stock")({
  head: () => ({
    meta: [
      { title: "Stock — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Entrées, sorties et ajustements de stock avec historique complet des mouvements du magasin.",
      },
      { property: "og:title", content: "Stock — DJIBEXA" },
      { property: "og:description", content: "Suivi des mouvements de stock en temps réel." },
    ],
  }),
  component: () => (
    <RequirePermission permission="stock.view">
      <Stock />
    </RequirePermission>
  ),
});

type StockImportMode = "catalog" | "initial" | "inventory";
type StockImportPreview = {
  id: number;
  mode: Exclude<StockImportMode, "catalog">;
  source_name: string;
  reason: string;
  status: string;
  rows: {
    line: number;
    reference: string;
    product_name: string;
    quantity: number | null;
    location_id: number | null;
    location: string;
    errors: string[];
  }[];
  total_rows: number;
  valid_rows: number;
  error_rows: number;
};

function Stock() {
  const { t } = useLocale();
  const { can } = useAuth();
  const canManageStock = can("stock.manage");
  const canManageInventory = can("inventory.manage");
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [productId, setProductId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [type, setType] = useState("entree");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<StockImportMode>("catalog");
  const [importReason, setImportReason] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<StockImportPreview | null>(null);

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
        }>("products/")
      ).map((product) => ({
        id: String(product.id),
        name: product.name,
        reference: product.sku,
        stock: product.quantity,
        alert_threshold: product.alert_threshold,
      })),
  });

  const { data: movements } = useQuery({
    queryKey: ["movements"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          movement_type: string;
          quantity: number;
          reference: string;
          product_name: string;
          created_at: string;
        }>("inventory/movements/")
      )
        .slice(0, 50)
        .map((movement) => ({
          id: String(movement.id),
          type: movement.movement_type,
          quantity: movement.quantity,
          created_at: movement.created_at,
          products: { name: movement.product_name },
        })),
  });

  const { data: locations } = useQuery({
    queryKey: ["stock-locations"],
    queryFn: async () => {
      const [stockItems, products, warehouses] = await Promise.all([
        api.list<{
          id: number;
          product: number;
          location: number;
          quantity: number;
        }>("inventory/stock/"),
        api.list<{
          id: number;
          name: string;
          sku: string;
          purchase_price: string;
          selling_price: string;
          alert_threshold: number;
        }>("products/"),
        api.list<{ id: number; name: string; location_type: string }>("inventory/locations/"),
      ]);
      const productById = new Map(products.map((product) => [product.id, product]));
      const locationById = new Map(warehouses.map((warehouse) => [warehouse.id, warehouse]));
      return stockItems.map((item) => {
        const product = productById.get(item.product);
        const warehouse = locationById.get(item.location);
        return {
          id: String(item.id),
          quantity: item.quantity,
          warehouse_id: String(item.location),
          products: product
            ? {
                name: product.name,
                reference: product.sku,
                purchase_price: product.purchase_price,
                sale_price: product.selling_price,
                alert_threshold: product.alert_threshold,
              }
            : null,
          warehouses: warehouse
            ? {
                name: warehouse.name,
                kind: warehouse.location_type,
                is_shop: warehouse.location_type === "shop",
              }
            : null,
        };
      });
    },
  });

  const { data: availableLocations } = useQuery({
    queryKey: ["stock-location-options"],
    queryFn: () =>
      api
        .list<{ id: number; name: string }>("inventory/locations/")
        .then((rows) => rows.map((location) => ({ id: String(location.id), name: location.name }))),
  });

  const [warehouseFilter, setWarehouseFilter] = useState("all");

  const rows = (locations ?? []).filter(
    (l) => warehouseFilter === "all" || l.warehouse_id === warehouseFilter,
  );
  const warehouseOptions = Array.from(
    new Map(
      (locations ?? []).map((l) => [l.warehouse_id, l.warehouses?.name ?? "—"] as const),
    ).entries(),
  );
  const totalUnits = rows.reduce((s, l) => s + l.quantity, 0);
  const movementQuantity = Number(quantity);
  const invalidMovementQuantity =
    quantity !== "" && (!Number.isInteger(movementQuantity) || movementQuantity <= 0);
  const buyValue = rows.reduce(
    (s, l) => s + l.quantity * Number(l.products?.purchase_price ?? 0),
    0,
  );
  const sellValue = rows.reduce((s, l) => s + l.quantity * Number(l.products?.sale_price ?? 0), 0);
  const alerts = (products ?? []).filter((p) => p.stock <= p.alert_threshold).length;
  const ranked = [...rows].sort(
    (a, b) =>
      b.quantity * Number(b.products?.sale_price ?? 0) -
      a.quantity * Number(a.products?.sale_price ?? 0),
  );

  const add = useMutation({
    mutationFn: async () => {
      if (!locationId) throw new Error(t("stock.chooseLocationError"));
      await api.post("inventory/movements/", {
        product: Number(productId),
        location: Number(locationId),
        movement_type: type === "entree" ? "in" : type === "sortie" ? "out" : "adjustment",
        quantity: Number(quantity),
        reference:
          reason ||
          (type === "entree"
            ? t("stock.inboundGoods")
            : type === "sortie"
              ? t("stock.outboundGoods")
              : t("stock.adjustment")),
        notes: reason,
      });
    },
    onSuccess: () => {
      toast.success(t("stock.movementSaved"));
      setOpen(false);
      setQuantity("");
      setReason("");
      void qc.invalidateQueries({ queryKey: ["movements"] });
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["stock-locations"] });
    },
    onError: (e: Error) => toast.error(t("stock.operationError"), { description: e.message }),
  });

  const previewStockImport = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      body.append("mode", importMode);
      body.append("reason", importReason);
      return api.post<StockImportPreview>("inventory/stock-import/", body);
    },
    onSuccess: setImportPreview,
    onError: (error: Error) =>
      toast.error(t("stock.importPreviewError"), { description: error.message }),
  });

  const confirmStockImport = useMutation({
    mutationFn: () =>
      api.post<{
        summary: { rows: number; locations: number; inventory_counts: number[] };
      }>(`inventory/stock-import/${importPreview?.id}/confirm/`, {}),
    onSuccess: (result) => {
      toast.success(
        t("stock.importSubmitted", {
          rows: result.summary.rows,
          locations: result.summary.locations,
        }),
      );
      setImportOpen(false);
      setImportPreview(null);
      setImportReason("");
      void qc.invalidateQueries({ queryKey: ["inventories"] });
    },
    onError: (error: Error) =>
      toast.error(t("stock.importConfirmError"), { description: error.message }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("nav.stock")}</h1>
          <p className="text-muted-foreground text-sm">{t("stock.summary")}</p>
        </div>
        {canManageStock && (
          <Button
            onClick={() => {
              setType("entree");
              setOpen(true);
            }}
          >
            <PackagePlus className="size-4" /> {t("stock.newEntry")}
          </Button>
        )}
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label={t("stock.actions")}>
        {canManageInventory && (
          <>
            <Button
              variant="outline"
              className="h-auto min-h-24 justify-start whitespace-normal p-4 text-left"
              onClick={() => {
                setImportPreview(null);
                setImportReason("");
                setImportMode("catalog");
                setImportOpen(true);
              }}
            >
              <FileUp className="size-5 shrink-0" />
              <span>
                <span className="block font-semibold">{t("stock.importFile")}</span>
                <span className="text-muted-foreground block text-xs font-normal">
                  {t("stock.importFileDescription")}
                </span>
              </span>
            </Button>
          </>
        )}
        {canManageInventory && (
          <Link
            to="/stock-manuel"
            className="panel flex min-h-24 items-center gap-3 p-4 transition-colors hover:bg-accent"
          >
            <PencilLine className="text-primary size-5 shrink-0" />
            <span>
              <span className="block font-semibold">{t("stock.adjustStock")}</span>
              <span className="text-muted-foreground block text-xs">
                {t("stock.adjustStockDescription")}
              </span>
            </span>
          </Link>
        )}
        <Button
          variant="outline"
          className="h-auto min-h-24 justify-start whitespace-normal p-4 text-left"
          onClick={() =>
            document
              .getElementById("stock-movement-history")
              ?.scrollIntoView({ behavior: "smooth" })
          }
        >
          <History className="size-5 shrink-0" />
          <span>
            <span className="block font-semibold">{t("stock.movements")}</span>
            <span className="text-muted-foreground block text-xs font-normal">
              {t("stock.movementsDescription")}
            </span>
          </span>
        </Button>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: t("stock.storedItems"), value: String(totalUnits) },
          { label: t("stock.purchaseValue"), value: money(buyValue) },
          { label: t("stock.saleValue"), value: money(sellValue) },
          { label: t("stock.alertProducts"), value: String(alerts) },
        ].map((k) => (
          <div key={k.label} className="panel p-4">
            <p className="text-muted-foreground text-xs tracking-widest uppercase">{k.label}</p>
            <p className="text-2xl font-bold">{k.value}</p>
          </div>
        ))}
      </div>

      <div className="panel overflow-x-auto">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b p-3">
          <span className="text-sm font-semibold uppercase">{t("stock.inventoryByLocation")}</span>
          <Select value={warehouseFilter} onValueChange={setWarehouseFilter}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("stock.allLocations")}</SelectItem>
              {warehouseOptions.map(([id, name]) => (
                <SelectItem key={id} value={id}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("stock.goods")}</TableHead>
              <TableHead>{t("stock.location")}</TableHead>
              <TableHead className="text-right">{t("stock.level")}</TableHead>
              <TableHead className="hidden text-right sm:table-cell">
                {t("stock.purchaseValue")}
              </TableHead>
              <TableHead className="text-right">{t("stock.saleValue")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ranked.map((l) => {
              const low = l.quantity <= Number(l.products?.alert_threshold ?? 0);
              return (
                <TableRow key={l.id}>
                  <TableCell>
                    <p className="font-medium">{l.products?.name ?? "—"}</p>
                    <p className="text-muted-foreground font-mono text-xs">
                      {l.products?.reference}
                    </p>
                  </TableCell>
                  <TableCell>
                    {l.warehouses?.name ?? "—"}
                    {l.warehouses?.is_shop && (
                      <span className="text-muted-foreground text-xs"> · {t("stock.shop")}</span>
                    )}
                  </TableCell>
                  <TableCell
                    className={`text-right font-semibold ${low ? "text-destructive" : ""}`}
                  >
                    {l.quantity}
                  </TableCell>
                  <TableCell className="hidden text-right sm:table-cell">
                    {money(l.quantity * Number(l.products?.purchase_price ?? 0))}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {money(l.quantity * Number(l.products?.sale_price ?? 0))}
                  </TableCell>
                </TableRow>
              );
            })}
            {!ranked.length && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                  {t("stock.noLocationStock")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel overflow-x-auto">
          <div className="border-b p-3 text-sm font-semibold uppercase">{t("stock.levels")}</div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("stock.product")}</TableHead>
                <TableHead className="text-right">{t("nav.stock")}</TableHead>
                <TableHead className="text-right">{t("stock.threshold")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(products ?? []).map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <p className="font-medium">{p.name}</p>
                    <p className="text-muted-foreground font-mono text-xs">{p.reference}</p>
                  </TableCell>
                  <TableCell
                    className={`text-right font-semibold ${p.stock <= p.alert_threshold ? "text-destructive" : ""}`}
                  >
                    {p.stock}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    {p.alert_threshold}
                  </TableCell>
                </TableRow>
              ))}
              {!products?.length && (
                <TableRow>
                  <TableCell colSpan={3} className="text-muted-foreground py-8 text-center">
                    {t("products.none")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <div id="stock-movement-history" className="panel overflow-x-auto">
          <div className="border-b p-3 text-sm font-semibold uppercase">{t("stock.movements")}</div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("stock.product")}</TableHead>
                <TableHead>{t("stock.type")}</TableHead>
                <TableHead className="text-right">{t("stock.quantity")}</TableHead>
                <TableHead className="hidden text-right sm:table-cell">
                  {t("credits.date")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(movements ?? []).map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.products?.name ?? "—"}</TableCell>
                  <TableCell>
                    {m.type === "in" || m.type === "entree"
                      ? t("stock.inboundGoods")
                      : m.type === "out" || m.type === "sortie"
                        ? t("stock.outboundGoods")
                        : m.type === "adjustment" || m.type === "ajustement"
                          ? t("stock.adjustment")
                          : m.type}
                  </TableCell>
                  <TableCell className="text-right">{m.quantity}</TableCell>
                  <TableCell className="text-muted-foreground hidden text-right text-xs sm:table-cell">
                    {dateTime(m.created_at)}
                  </TableCell>
                </TableRow>
              ))}
              {!movements?.length && (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground py-8 text-center">
                    {t("stock.noMovements")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("stock.movementTitle")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{t("stock.product")}</Label>
              <Select value={productId} onValueChange={setProductId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("stock.chooseProduct")} />
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
            <div className="space-y-1.5">
              <Label>{t("stock.location")}</Label>
              <Select value={locationId} onValueChange={setLocationId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("stock.chooseLocation")} />
                </SelectTrigger>
                <SelectContent>
                  {(availableLocations ?? []).map((location) => (
                    <SelectItem key={location.id} value={location.id}>
                      {location.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("stock.type")}</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="entree">{t("stock.inboundGoods")}</SelectItem>
                  <SelectItem value="sortie">{t("stock.outboundGoods")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("stock.quantity")}</Label>
              <Input
                type="number"
                min={1}
                step="1"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("stock.reason")}</Label>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => add.mutate()}
              disabled={
                !productId ||
                !locationId ||
                quantity === "" ||
                invalidMovementQuantity ||
                add.isPending
              }
            >
              {t("stock.saveMovement")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={importOpen}
        onOpenChange={(nextOpen) => {
          setImportOpen(nextOpen);
          if (!nextOpen) {
            setImportPreview(null);
            setImportReason("");
            setImportFile(null);
          }
        }}
      >
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("stock.importFile")}</DialogTitle>
            <DialogDescription>{t("stock.importModesDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>{t("stock.importMode")}</Label>
              <Select
                value={importMode}
                onValueChange={(value: StockImportMode) => {
                  setImportMode(value);
                  setImportPreview(null);
                  setImportFile(null);
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="catalog">{t("stock.importCatalog")}</SelectItem>
                  <SelectItem value="initial">{t("stock.importInitial")}</SelectItem>
                  <SelectItem value="inventory">{t("stock.importPhysicalCount")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {importMode === "catalog" ? (
              <div className="rounded-md border p-4">
                <p className="text-sm">{t("stock.catalogImportDescription")}</p>
                <Button asChild className="mt-3">
                  <Link to="/produits/">{t("stock.openCatalogImport")}</Link>
                </Button>
              </div>
            ) : (
              <>
                <p className="text-muted-foreground text-sm">
                  {t(
                    importMode === "initial"
                      ? "stock.initialImportDescription"
                      : "stock.physicalImportDescription",
                  )}
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="stock-import-reason">{t("stock.reason")}</Label>
                  <Input
                    id="stock-import-reason"
                    value={importReason}
                    onChange={(event) => {
                      setImportReason(event.target.value);
                      setImportPreview(null);
                    }}
                    maxLength={500}
                  />
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      void api
                        .download("inventory/stock-import/template/", "modele-stock-djibexa.csv")
                        .catch((error: Error) =>
                          toast.error(t("stock.importPreviewError"), {
                            description: error.message,
                          }),
                        )
                    }
                  >
                    {t("stock.downloadStockTemplate")}
                  </Button>
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <Label htmlFor="stock-import-file">{t("stock.importFile")}</Label>
                    <Input
                      id="stock-import-file"
                      type="file"
                      accept=".csv,.xlsx"
                      disabled={previewStockImport.isPending}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        setImportFile(file ?? null);
                        setImportPreview(null);
                        event.currentTarget.value = "";
                      }}
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={!importFile || !importReason.trim() || previewStockImport.isPending}
                    onClick={() => {
                      if (importFile) previewStockImport.mutate(importFile);
                    }}
                  >
                    {previewStockImport.isPending
                      ? t("stock.importPreviewing")
                      : t("stock.previewImportFile")}
                  </Button>
                </div>
                {importPreview && (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-3 rounded-md border p-3 text-sm">
                      <strong>{importPreview.source_name}</strong>
                      <span>{t("stock.importRows", { count: importPreview.total_rows })}</span>
                      <span className="text-emerald-700">
                        {t("stock.importValidRows", { count: importPreview.valid_rows })}
                      </span>
                      {importPreview.error_rows > 0 && (
                        <span className="text-destructive">
                          {t("stock.importErrorRows", { count: importPreview.error_rows })}
                        </span>
                      )}
                    </div>
                    <div className="max-h-72 overflow-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{t("stock.importLine")}</TableHead>
                            <TableHead>{t("products.internalReference")}</TableHead>
                            <TableHead>{t("stock.product")}</TableHead>
                            <TableHead>{t("stock.location")}</TableHead>
                            <TableHead className="text-right">{t("stock.countedStock")}</TableHead>
                            <TableHead>{t("stock.importValidation")}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {importPreview.rows.map((row) => (
                            <TableRow key={row.line}>
                              <TableCell>{row.line}</TableCell>
                              <TableCell className="font-mono">{row.reference || "—"}</TableCell>
                              <TableCell>{row.product_name || "—"}</TableCell>
                              <TableCell>{row.location || "—"}</TableCell>
                              <TableCell className="text-right">{row.quantity ?? "—"}</TableCell>
                              <TableCell
                                className={
                                  row.errors.length ? "text-destructive" : "text-emerald-700"
                                }
                              >
                                {row.errors.length
                                  ? row.errors.join(" ")
                                  : t("stock.importRowValid")}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
          {importMode !== "catalog" && (
            <DialogFooter>
              <Button
                disabled={
                  !importPreview ||
                  importPreview.error_rows > 0 ||
                  importPreview.total_rows === 0 ||
                  confirmStockImport.isPending
                }
                onClick={() => confirmStockImport.mutate()}
              >
                {confirmStockImport.isPending
                  ? t("stock.importSubmitting")
                  : t("stock.importSubmitForValidation")}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
