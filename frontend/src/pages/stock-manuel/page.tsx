import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { PencilLine, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { RequirePermission } from "@/components/RequirePermission";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { docNumber } from "@/lib/qr";

export const PageRoute = createFileRoute("/_authenticated/stock-manuel")({
  head: () => ({
    meta: [
      { title: "Saisie manuelle du stock — ERP DJIBEXA" },
      {
        name: "description",
        content: "Saisir à la main la quantité d'un produit dans chaque dépôt.",
      },
      { property: "og:title", content: "Saisie manuelle du stock — DJIBEXA" },
      {
        property: "og:description",
        content: "Correction manuelle des quantités par produit et dépôt.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequirePermission permission="inventory.manage">
      <ManualStockPage />
    </RequirePermission>
  ),
});

function ManualStockPage() {
  const { t } = useLocale();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [productId, setProductId] = useState<string | null>(null);
  const [warehouseId, setWarehouseId] = useState("");
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("");

  const products = useQuery({
    queryKey: ["manual-products", q],
    enabled: q.trim().length >= 2,
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          name: string;
          sku: string;
          brand: string;
        }>("products/", { search: q.trim() })
      )
        .slice(0, 20)
        .map((product) => ({
          id: String(product.id),
          name: product.name,
          reference: product.sku,
          brand: product.brand,
        })),
  });

  const warehouses = useQuery({
    queryKey: ["warehouses-list"],
    queryFn: async () =>
      (await api.list<{ id: number; name: string }>("inventory/locations/")).map((location) => ({
        id: String(location.id),
        name: location.name,
      })),
  });

  const stock = useQuery({
    queryKey: ["manual-stock", productId],
    enabled: !!productId,
    queryFn: async () =>
      (await api.list<{ location: number; product: number; quantity: number }>("inventory/stock/"))
        .filter((row) => String(row.product) === productId)
        .map((row) => ({ warehouse_id: String(row.location), quantity: row.quantity })),
  });

  const current = useMemo(
    () => stock.data?.find((r) => r.warehouse_id === warehouseId)?.quantity ?? 0,
    [stock.data, warehouseId],
  );
  const selected = products.data?.find((p) => p.id === productId);

  const save = useMutation({
    mutationFn: async () => {
      const n = Number(qty);
      const normalizedReason = reason.trim();
      if (!productId || !warehouseId || !Number.isInteger(n) || n < 0 || !normalizedReason) {
        throw new Error(t("manualStock.invalidFields"));
      }
      if (n === current) return { unchanged: true };

      const inventory = await api.post<{
        id: number;
        items: { id: number; product: number }[];
      }>("inventory/counts/", {
        number: docNumber("INV"),
        period_type: "journalier",
        location: Number(warehouseId),
        notes: normalizedReason,
      });
      const line = inventory.items.find((item) => item.product === Number(productId));
      if (!line) {
        throw new Error(t("manualStock.inventoryLineMissing", { id: inventory.id }));
      }
      await api.patch(`inventory/counts/${inventory.id}/`, {
        notes: normalizedReason,
        items: [{ id: line.id, counted_quantity: n }],
      });
      await api.post(`inventory/counts/${inventory.id}/submit/`);
      return { unchanged: false };
    },
    onSuccess: (result) => {
      toast.success(result.unchanged ? t("manualStock.saved") : t("inventory.submittedToast"));
      setQty("");
      setReason("");
      void qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="font-display text-2xl font-bold uppercase">{t("manualStock.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("manualStock.description")}</p>
      </div>

      <div className="panel space-y-3 p-5">
        <Label htmlFor="q">{t("manualStock.searchProduct")}</Label>
        <div className="relative">
          <Search className="text-muted-foreground absolute top-2.5 left-3 size-4" />
          <Input
            id="q"
            className="pl-9"
            placeholder={t("manualStock.searchPlaceholder")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="max-h-64 space-y-1 overflow-y-auto">
          {products.data?.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setProductId(p.id)}
              className={`w-full rounded border px-3 py-2 text-left text-sm ${p.id === productId ? "border-primary bg-primary/10" : "hover:bg-muted"}`}
            >
              <span className="font-medium">{p.name}</span>
              <span className="text-muted-foreground ml-2 font-mono text-xs">
                {p.reference}
                {p.brand ? ` · ${p.brand}` : ""}
              </span>
            </button>
          ))}
          {products.data?.length === 0 && (
            <p className="text-muted-foreground text-sm">{t("manualStock.noProduct")}</p>
          )}
          {products.isError && (
            <p className="text-destructive text-sm">{t("manualStock.productsError")}</p>
          )}
        </div>
      </div>

      {productId && (
        <div className="panel space-y-4 p-5">
          <p className="font-semibold">2. {selected?.name}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("manualStock.location")}</Label>
              <Select value={warehouseId} onValueChange={setWarehouseId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("manualStock.chooseLocation")} />
                </SelectTrigger>
                <SelectContent>
                  {warehouses.data?.map((w) => (
                    <SelectItem key={w.id} value={w.id}>
                      {w.name} ({stock.data?.find((r) => r.warehouse_id === w.id)?.quantity ?? 0})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qty">
                {t("manualStock.newQuantity")}{" "}
                {warehouseId && t("manualStock.current", { quantity: current })}
              </Label>
              <Input
                id="qty"
                type="number"
                min={0}
                step={1}
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="reason">{t("manualStock.reason")}</Label>
              <Input
                id="reason"
                placeholder={t("manualStock.reasonExample")}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
              />
            </div>
          </div>
          <Button
            disabled={
              !warehouseId ||
              qty === "" ||
              !Number.isInteger(Number(qty)) ||
              Number(qty) < 0 ||
              Number(qty) === current ||
              !reason.trim() ||
              save.isPending
            }
            onClick={() => save.mutate()}
          >
            <PencilLine className="size-4" /> {t("manualStock.saveQuantity")}
          </Button>
        </div>
      )}
    </div>
  );
}
