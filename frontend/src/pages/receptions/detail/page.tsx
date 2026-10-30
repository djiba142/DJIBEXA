import { Route as FileRoute } from "@/routes/_authenticated/receptions/$receptionId";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/receptions/$receptionId")({
  head: () => ({
    meta: [
      { title: "Détail réception — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Quantités reçues, frais réels, coût de revient unitaire et fixation du prix de vente.",
      },
      { property: "og:title", content: "Réception — DJIBEXA" },
      { property: "og:description", content: "Coût réel d'approvisionnement et prix de vente." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="receptions.view">
      <ReceptionDetail />
    </RequirePermission>
  ),
});

type Draft = {
  received: string;
  accepted: string;
  quarantined: string;
  reason: string;
  cost: string;
  margin: string;
  price: string;
  itemsPerCarton: string;
  supplierReference: string;
  supplierBarcode: string;
};

const FEES = [
  ["transport_cost", "receipts.fee.transport"],
  ["customs_cost", "receipts.fee.customs"],
  ["handling_cost", "receipts.fee.handling"],
  ["insurance_cost", "receipts.fee.insurance"],
  ["other_cost", "receipts.fee.other"],
] as const;

function ReceptionDetail() {
  const { receptionId } = FileRoute.useParams();
  const { t } = useLocale();
  const { can, hasRole } = useAuth();
  const manage = can("receptions.manage");
  const manageCosts = can("purchases.manage");
  const canValidate = hasRole("admin");
  const qc = useQueryClient();

  const [fees, setFees] = useState<Record<string, string>>({});
  const [method, setMethod] = useState("value");
  const [notes, setNotes] = useState("");
  const [locationId, setLocationId] = useState("");
  const [discrepancyReason, setDiscrepancyReason] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [reviewedItemIds, setReviewedItemIds] = useState<number[]>([]);
  const { data, isLoading } = useQuery({
    queryKey: ["reception", receptionId],
    queryFn: async () => {
      const reception = await api.get<{
        id: number;
        reference: string;
        purchase_order: number;
        location: number | null;
        status: string;
        version: number;
        supplier_document_reference: string;
        notes: string;
        discrepancy_reason: string;
        decision_reason: string;
        submitted_by: number | null;
        reviewed_at: string | null;
        allocation_method: string;
        received_date: string;
        transport_cost?: string;
        customs_cost?: string;
        handling_cost?: string;
        insurance_cost?: string;
        other_cost?: string;
        items: {
          id: number;
          product: number;
          quantity_received: number;
          quantity_accepted: number;
          quantity_quarantined: number;
          discrepancy_reason: string;
          unit_cost?: string;
          real_unit_cost?: string;
          items_per_carton: number;
          supplier_reference: string;
          supplier_barcode: string;
          supplier_lot_reference: string;
          condition_status: string;
          packaging_condition: string;
          notes: string;
        }[];
      }>(`purchases/receipts/${receptionId}/`);
      const [order, products, locations] = await Promise.all([
        api.get<{
          reference: string;
          supplier: number;
          supplier_name: string;
          items: { product: number; quantity: number }[];
        }>(`purchases/orders/${reception.purchase_order}/`),
        api.list<{ id: number; name: string; sku: string; selling_price: string }>("products/"),
        api.list<{ id: number; name: string }>("inventory/locations/"),
      ]);
      return {
        reception: {
          ...reception,
          number: reception.reference,
          created_at: reception.received_date,
          validated_at: reception.status === "received" ? reception.received_date : null,
          suppliers: { name: order.supplier_name },
          warehouses: locations.find((location) => location.id === reception.location),
          purchase_orders: { number: order.reference },
          freight_cost: reception.transport_cost,
          items: reception.items.map((item) => {
            const product = products.find((entry) => entry.id === item.product);
            return {
              ...item,
              ordered_quantity:
                order.items.find((line) => line.product === item.product)?.quantity ?? 0,
              items_per_carton: item.items_per_carton,
              supplier_reference: item.supplier_reference,
              supplier_barcode: item.supplier_barcode,
              supplier_lot_reference: item.supplier_lot_reference,
              condition_status: item.condition_status,
              packaging_condition: item.packaging_condition,
              real_unit_cost: item.real_unit_cost ?? "0",
              products: {
                name: product?.name ?? "",
                reference: product?.sku ?? "",
                sale_price: product?.selling_price ?? "0",
              },
            };
          }),
        },
        items: reception.items.map((item) => {
          const product = products.find((entry) => entry.id === item.product);
          return {
            ...item,
            id: String(item.id),
            product_id: item.product,
            ordered_quantity:
              order.items.find((line) => line.product === item.product)?.quantity ?? 0,
            received_quantity: item.quantity_received,
            items_per_carton: item.items_per_carton,
            supplier_reference: item.supplier_reference,
            supplier_barcode: item.supplier_barcode,
            supplier_lot_reference: item.supplier_lot_reference,
            condition_status: item.condition_status,
            packaging_condition: item.packaging_condition,
            real_unit_cost: Number(item.unit_cost ?? 0),
            allocated_fees: Number(item.real_unit_cost ?? 0) - Number(item.unit_cost ?? 0),
            real_cost_unit: Number(item.real_unit_cost ?? 0),
            new_sale_price: null,
            products: {
              name: product?.name ?? "",
              reference: product?.sku ?? "",
              sale_price: product?.selling_price ?? "0",
            },
          };
        }),
        locations,
      };
    },
  });

  const reception = data?.reception;
  const items = useMemo(() => data?.items ?? [], [data]);
  const canEdit = Boolean(
    manage && reception && ["draft", "changes_requested"].includes(reception.status),
  );
  const locked = !canEdit;

  useEffect(() => {
    if (!reception) return;
    setFees(Object.fromEntries(FEES.map(([k]) => [k, String(reception[k] ?? 0)])));
    setMethod(reception.allocation_method);
    setNotes(reception.notes ?? "");
    setLocationId(reception.location === null ? "" : String(reception.location));
    setDiscrepancyReason(reception.discrepancy_reason ?? "");
    setReviewedItemIds([]);
    setDrafts(
      Object.fromEntries(
        items.map((it) => [
          it.id,
          {
            received: String(it.received_quantity),
            accepted: String(it.quantity_accepted),
            quarantined: String(it.quantity_quarantined),
            reason: it.discrepancy_reason ?? "",
            cost: String(it.real_unit_cost),
            margin: "30",
            price: String(it.new_sale_price ?? it.products?.sale_price ?? 0),
            itemsPerCarton: String(it.items_per_carton),
            supplierReference: it.supplier_reference,
            supplierBarcode: it.supplier_barcode,
          },
        ]),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const totalFees = FEES.reduce((sum, [k]) => sum + (Number(fees[k]) || 0), 0);

  const computed = useMemo(() => {
    const base = items.map((it) => {
      const d = drafts[it.id];
      const received = Number(d?.received) || 0;
      const cost = Number(d?.cost) || 0;
      const weight = method === "quantity" ? received : received * cost;
      return { id: it.id, received, cost, weight };
    });
    const totalWeight = base.reduce((s, b) => s + b.weight, 0);
    return Object.fromEntries(
      base.map((b) => {
        const allocated = totalWeight > 0 ? (totalFees * b.weight) / totalWeight : 0;
        const unit = b.received > 0 ? b.cost + allocated / b.received : b.cost;
        return [b.id, { allocated, unit, merchandise: b.received * b.cost }];
      }),
    );
  }, [items, drafts, method, totalFees]);

  const merchandiseTotal = Object.values(computed).reduce((s, c) => s + c.merchandise, 0);
  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        notes,
        location: locationId ? Number(locationId) : null,
        discrepancy_reason: discrepancyReason,
        ...(manageCosts && {
          allocation_method: method,
          transport_cost: Number(fees["transport_cost"]) || 0,
          customs_cost: Number(fees["customs_cost"]) || 0,
          handling_cost: Number(fees["handling_cost"]) || 0,
          insurance_cost: Number(fees["insurance_cost"]) || 0,
          other_cost: Number(fees["other_cost"]) || 0,
        }),
        items: items.map((item) => ({
          product: item.product_id,
          quantity_received: Number(drafts[item.id]?.received) || 0,
          quantity_accepted: Number(drafts[item.id]?.accepted) || 0,
          quantity_quarantined: Number(drafts[item.id]?.quarantined) || 0,
          discrepancy_reason: drafts[item.id]?.reason ?? "",
          ...(manageCosts && { unit_cost: Number(drafts[item.id]?.cost) || 0 }),
          items_per_carton: Number(drafts[item.id]?.itemsPerCarton) || item.received_quantity,
          supplier_reference: drafts[item.id]?.supplierReference ?? "",
          supplier_barcode: drafts[item.id]?.supplierBarcode ?? "",
        })),
      };
      await api.patch(`purchases/receipts/${receptionId}/`, payload);
      if (manageCosts) {
        for (const item of items) {
          const price = Number(drafts[item.id]?.price);
          if (price > 0) {
            await api.patch(`products/${item.product_id}/`, { selling_price: price });
          }
        }
      }
    },
    onSuccess: () => {
      toast.success(t("receipts.saved"));
      void qc.invalidateQueries({ queryKey: ["reception", receptionId] });
    },
    onError: (e: Error) => toast.error(t("receipts.saveError"), { description: e.message }),
  });

  const validate = useMutation({
    mutationFn: async () => {
      if (!reception) throw new Error(t("receipts.notFound"));
      await api.post(`purchases/receipts/${receptionId}/validate/`, {
        version: reception.version,
        reviewed_item_ids: reviewedItemIds,
      });
    },
    onSuccess: () => {
      toast.success(t("receipts.validatedToast"), {
        description: t("receipts.validatedDescription"),
      });
      void qc.invalidateQueries({ queryKey: ["reception", receptionId] });
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["stock"] });
      void qc.invalidateQueries({ queryKey: ["movements"] });
    },
    onError: (e: Error) => toast.error(t("receipts.validateError"), { description: e.message }),
  });

  const submit = useMutation({
    mutationFn: async () => {
      await save.mutateAsync();
      await api.post(`purchases/receipts/${receptionId}/submit/`);
    },
    onSuccess: () => {
      toast.success(t("receipts.submittedToast"));
      void qc.invalidateQueries({ queryKey: ["reception", receptionId] });
    },
    onError: (e: Error) => toast.error(t("receipts.submitError"), { description: e.message }),
  });

  const decision = useMutation({
    mutationFn: async (action: "reject" | "request-correction" | "hold" | "resume") => {
      const reason = window.prompt(t("receipts.decisionReason"));
      if (!reason?.trim()) throw new Error(t("receipts.reasonRequired"));
      await api.post(`purchases/receipts/${receptionId}/decision/${action}/`, { reason });
    },
    onSuccess: () => {
      toast.success(t("receipts.decisionSaved"));
      void qc.invalidateQueries({ queryKey: ["reception", receptionId] });
    },
    onError: (e: Error) => toast.error(t("receipts.decisionError"), { description: e.message }),
  });

  const patch = (id: string, key: keyof Draft, value: string) =>
    setDrafts((prev) => {
      const current = prev[id];
      if (!current) return prev;
      const next = { ...current, [key]: value };
      return { ...prev, [id]: next };
    });

  if (isLoading) return <p className="text-muted-foreground text-sm">{t("receipts.loading")}</p>;

  if (!reception) {
    return (
      <div className="panel mx-auto max-w-md p-6 text-center">
        <h1 className="text-lg font-semibold">{t("receipts.notFound")}</h1>
        <Button asChild className="mt-4">
          <Link to="/receptions">{t("receipts.back")}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Button variant="outline" asChild>
        <Link to="/receptions">
          <ArrowLeft className="size-4" /> {t("receipts.backShort")}
        </Link>
      </Button>

      <div className="panel space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3">
          <div>
            <h1 className="font-display text-xl font-bold uppercase">
              {t("receipts.title")} {reception.number}
            </h1>
            <p className="text-muted-foreground text-xs">
              {reception.suppliers?.name ?? t("receipts.unknownSupplier")}
              {reception.purchase_orders?.number
                ? ` · ${reception.purchase_orders.number}`
                : ""} · {reception.warehouses?.name ?? t("receipts.unknownLocation")} ·{" "}
              {dateTime(reception.created_at)}
            </p>
            {reception.supplier_document_reference && (
              <p className="text-muted-foreground text-xs">
                {t("receipts.supplierDocumentReference")}: {reception.supplier_document_reference}
              </p>
            )}
          </div>
          <Badge variant={reception.status === "received" ? "default" : "secondary"}>
            {reception.status === "received"
              ? t("receipts.validated")
              : reception.status === "draft"
                ? t("receipts.draft")
                : t(`receipts.status.${reception.status}`)}
          </Badge>
        </div>

        <div className="space-y-3">
          <p className="text-sm font-semibold uppercase">{t("receipts.goodsReceived")}</p>
          {items.map((it) => {
            const d = drafts[it.id];
            const c = computed[it.id];
            const currentPrice = Number(it.products?.sale_price ?? 0);
            return (
              <div key={it.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-medium">{it.products?.name}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {it.products?.reference} · {t("receipts.ordered")} {it.ordered_quantity}
                  </p>
                </div>
                {[
                  [t("receipts.supplierLotReference"), it.supplier_lot_reference],
                  [t("receipts.conditionStatus"), it.condition_status],
                  [t("receipts.packagingCondition"), it.packaging_condition],
                  [t("receipts.lineNotes"), it.notes],
                ].some(([, value]) => Boolean(value)) && (
                  <div className="text-muted-foreground mt-2 grid gap-1 text-xs sm:grid-cols-2">
                    {[
                      [t("receipts.supplierLotReference"), it.supplier_lot_reference],
                      [t("receipts.conditionStatus"), it.condition_status],
                      [t("receipts.packagingCondition"), it.packaging_condition],
                      [t("receipts.lineNotes"), it.notes],
                    ]
                      .filter(([, value]) => Boolean(value))
                      .map(([label, value]) => (
                        <p key={label}>
                          {label}: {value}
                        </p>
                      ))}
                  </div>
                )}
                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="space-y-1">
                    <Label className="text-xs">{t("receipts.quantityReceived")}</Label>
                    <Input
                      type="number"
                      min={0}
                      disabled={locked}
                      value={d?.received ?? ""}
                      onChange={(e) => patch(it.id, "received", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("receipts.quantityAccepted")}</Label>
                    <Input
                      type="number"
                      min={0}
                      disabled={locked}
                      value={d?.accepted ?? ""}
                      onChange={(e) => patch(it.id, "accepted", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("receipts.quantityQuarantined")}</Label>
                    <Input
                      type="number"
                      min={0}
                      disabled={locked}
                      value={d?.quarantined ?? ""}
                      onChange={(e) => patch(it.id, "quarantined", e.target.value)}
                    />
                  </div>
                  {manageCosts && (
                    <div className="space-y-1">
                      <Label className="text-xs">{t("receipts.actualPurchasePrice")}</Label>
                      <Input
                        type="number"
                        min={0}
                        disabled={locked}
                        value={d?.cost ?? ""}
                        onChange={(e) => patch(it.id, "cost", e.target.value)}
                      />
                    </div>
                  )}
                  <div className="space-y-1">
                    <Label className="text-xs">{t("receipts.itemsPerCarton")}</Label>
                    <Input
                      type="number"
                      min={1}
                      disabled={locked}
                      value={d?.itemsPerCarton ?? "1"}
                      onChange={(e) => patch(it.id, "itemsPerCarton", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("receipts.supplierReference")}</Label>
                    <Input
                      disabled={locked}
                      value={d?.supplierReference ?? ""}
                      onChange={(e) => patch(it.id, "supplierReference", e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t("receipts.supplierBarcode")}</Label>
                    <Input
                      disabled={locked}
                      value={d?.supplierBarcode ?? ""}
                      onChange={(e) => patch(it.id, "supplierBarcode", e.target.value)}
                    />
                  </div>
                  <div className="col-span-2 space-y-1 sm:col-span-4">
                    <Label className="text-xs">{t("receipts.discrepancyReason")}</Label>
                    <Input
                      disabled={locked}
                      value={d?.reason ?? ""}
                      onChange={(e) => patch(it.id, "reason", e.target.value)}
                    />
                  </div>
                </div>
                {manageCosts && canEdit && (
                  <div className="bg-muted/40 mt-3 grid grid-cols-2 gap-3 rounded-md p-3 text-sm sm:grid-cols-4">
                    <p>
                      {t("receipts.allocatedFees")}
                      <span className="block font-semibold">{money(c?.allocated ?? 0)}</span>
                    </p>
                    <p>
                      {t("receipts.actualUnitCost")}
                      <span className="text-primary block font-semibold">
                        {money(c?.unit ?? 0)}
                      </span>
                    </p>
                    <p>
                      {t("receipts.currentSalePrice")}
                      <span className="block font-semibold">{money(currentPrice)}</span>
                    </p>
                    <p>
                      {t("receipts.margin")}
                      <span
                        className={`block font-semibold ${
                          Number(d?.price ?? 0) - (c?.unit ?? 0) < 0 ? "text-destructive" : ""
                        }`}
                      >
                        {money(Number(d?.price ?? 0) - (c?.unit ?? 0))}
                      </span>
                    </p>
                  </div>
                )}
                {!locked && manageCosts && (
                  <div className="mt-3 flex flex-wrap items-end gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">{t("receipts.desiredMargin")}</Label>
                      <Input
                        type="number"
                        className="w-28"
                        value={d?.margin ?? ""}
                        onChange={(e) => patch(it.id, "margin", e.target.value)}
                      />
                    </div>
                    <Button
                      variant="outline"
                      onClick={() =>
                        patch(
                          it.id,
                          "price",
                          String(Math.round((c?.unit ?? 0) * (1 + (Number(d?.margin) || 0) / 100))),
                        )
                      }
                    >
                      {t("receipts.calculatePrice")}
                    </Button>
                    <div className="space-y-1">
                      <Label className="text-xs">{t("receipts.newSalePrice")}</Label>
                      <Input
                        type="number"
                        className="w-36"
                        value={d?.price ?? ""}
                        onChange={(e) => patch(it.id, "price", e.target.value)}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {!items.length && (
            <p className="text-muted-foreground text-sm">{t("receipts.noItems")}</p>
          )}
        </div>

        {manageCosts && (
          <div className="space-y-3 border-t pt-4">
            <p className="text-sm font-semibold uppercase">{t("receipts.actualFees")}</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {FEES.map(([key, labelKey]) => (
                <div key={key} className="space-y-1">
                  <Label className="text-xs">{t(labelKey)}</Label>
                  <Input
                    type="number"
                    min={0}
                    value={fees[key] ?? ""}
                    onChange={(e) => setFees((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("receipts.allocationMethod")}</Label>
                <Select value={method} onValueChange={setMethod}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="value">{t("receipts.byValue")}</SelectItem>
                    <SelectItem value="quantity">{t("receipts.byQuantity")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("receipts.observations")}</Label>
                <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
              </div>
            </div>
            <div className="bg-muted/40 rounded-md p-3 text-sm">
              <p className="flex justify-between">
                <span>{t("receipts.goods")}</span>
                <span>{money(merchandiseTotal)}</span>
              </p>
              <p className="flex justify-between">
                <span>{t("receipts.fees")}</span>
                <span>{money(totalFees)}</span>
              </p>
              <p className="mt-1 flex justify-between border-t pt-1 font-bold">
                <span>{t("receipts.totalActualCost")}</span>
                <span>{money(merchandiseTotal + totalFees)}</span>
              </p>
            </div>
          </div>
        )}

        {reception.status === "submitted" && (
          <div className="space-y-3 border-t pt-4">
            <p className="text-sm font-semibold">{t("receipts.reviewTitle")}</p>
            <p className="text-muted-foreground text-xs">{t("receipts.reviewHelp")}</p>
            {items.map((item) => {
              const itemId = Number(item.id);
              const checked = reviewedItemIds.includes(itemId);
              return (
                <Button
                  key={item.id}
                  type="button"
                  variant={checked ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    setReviewedItemIds((ids) =>
                      checked ? ids.filter((id) => id !== itemId) : [...ids, itemId],
                    )
                  }
                >
                  {checked ? t("receipts.lineReviewed") : t("receipts.reviewLine")} ·{" "}
                  {item.products?.name}
                </Button>
              );
            })}
            <p className="text-muted-foreground text-sm">
              {reception.decision_reason || t("receipts.pendingReview")}
            </p>
          </div>
        )}

        {locked && reception.status !== "submitted" ? (
          <p className="text-muted-foreground border-t pt-3 text-xs">
            {reception.status === "received"
              ? t("receipts.validatedReadOnly", {
                  date: dateTime(reception.reviewed_at ?? reception.created_at),
                })
              : t(`receipts.status.${reception.status}`)}
          </p>
        ) : (
          canEdit && (
            <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
              <div className="min-w-56 space-y-1">
                <Label className="text-xs">{t("receipts.storageLocation")}</Label>
                <Select value={locationId} onValueChange={setLocationId}>
                  <SelectTrigger>
                    <SelectValue placeholder={t("receipts.chooseLocation")} />
                  </SelectTrigger>
                  <SelectContent>
                    {data?.locations.map((location) => (
                      <SelectItem key={location.id} value={String(location.id)}>
                        {location.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="min-w-56 space-y-1">
                <Label className="text-xs">{t("receipts.discrepancyReason")}</Label>
                <Input
                  value={discrepancyReason}
                  onChange={(e) => setDiscrepancyReason(e.target.value)}
                />
              </div>
              <Button variant="outline" onClick={() => save.mutate()} disabled={save.isPending}>
                {t("receipts.save")}
              </Button>
              {manage && (
                <Button
                  onClick={() => submit.mutate()}
                  disabled={submit.isPending || !items.length || !locationId}
                >
                  {t("receipts.submit")}
                </Button>
              )}
            </div>
          )
        )}
        {canValidate && reception.status === "submitted" && (
          <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
            <Button variant="outline" onClick={() => decision.mutate("hold")}>
              {t("receipts.hold")}
            </Button>
            <Button variant="outline" onClick={() => decision.mutate("request-correction")}>
              {t("receipts.requestCorrection")}
            </Button>
            <Button variant="destructive" onClick={() => decision.mutate("reject")}>
              {t("receipts.reject")}
            </Button>
            <Button
              onClick={() => {
                if (window.confirm(t("receipts.validateConfirm"))) validate.mutate();
              }}
              disabled={validate.isPending || reviewedItemIds.length !== items.length}
            >
              {t("receipts.validate")}
            </Button>
          </div>
        )}
        {canValidate && reception.status === "on_hold" && (
          <div className="flex justify-end border-t pt-3">
            <Button onClick={() => decision.mutate("resume")}>{t("receipts.resumeReview")}</Button>
          </div>
        )}
      </div>
    </div>
  );
}
