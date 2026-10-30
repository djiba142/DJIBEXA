import { Route as FileRoute } from "@/routes/_authenticated/commandes/$orderId";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Download, Mail, Printer, Share2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PartnerStrip } from "@/components/PartnerStrip";
import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { buildPurchaseOrderPdf } from "@/lib/purchase-order-pdf";
import { downloadPdfBlob, shareOnWhatsApp } from "@/lib/document-pdf";
import { dateTime, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";
import { docQrValue, QrImage, siteOrigin } from "@/lib/qr";
import { statusVariant } from "@/lib/purchase-status";

export const PageRoute = createFileRoute("/_authenticated/commandes/$orderId")({
  head: () => ({
    meta: [
      { title: "Détail commande fournisseur — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Lignes commandées, quantités physiques reçues et contrôle avant mise à jour du stock.",
      },
      { property: "og:title", content: "Commande fournisseur — DJIBEXA" },
      {
        property: "og:description",
        content: "Réception de commande et validation avant l'entrée en stock.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="purchases.view">
      <OrderDetail />
    </RequirePermission>
  ),
});

function OrderDetail() {
  const { orderId } = FileRoute.useParams();
  const { t } = useLocale();
  const { can, hasRole } = useAuth();
  const manage = can("purchases.manage");
  const qc = useQueryClient();
  const [received, setReceived] = useState<Record<string, number>>({});
  const [locationId, setLocationId] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["purchase_order", orderId],
    queryFn: async () => {
      const [order, receipts, products, suppliers, locations] = await Promise.all([
        api.get<{
          id: number;
          supplier: number;
          reference: string;
          status: string;
          notes: string;
          order_date: string;
          currency: string;
          exchange_rate: string;
          exchange_rate_date: string | null;
          reference_exchange_rate: string | null;
          exchange_rate_reason: string;
          exchange_rate_applied_at: string | null;
          exchange_rate_applied_by_name: string;
          total_amount: string;
          items: { id: number; product: number; quantity: number; unit_cost?: string | null }[];
        }>(`purchase-orders/${orderId}/`),
        api.list<{
          purchase_order: number;
          status: string;
          items: { product: number; quantity_received: number }[];
        }>("receipts/"),
        api.list<{ id: number; name: string; sku: string }>("products/"),
        api.list<{
          id: number;
          name: string;
          company_name: string;
          contact_name: string;
          phone: string;
          email: string;
          address: string;
        }>("suppliers/"),
        api.list<{ id: number; name: string; location_type: string }>("locations/"),
      ]);
      const productById = new Map(products.map((product) => [product.id, product]));
      const supplier = suppliers.find((item) => item.id === order.supplier);
      const receivedByProduct = new Map<number, number>();
      for (const receipt of receipts) {
        if (
          receipt.purchase_order !== order.id ||
          !["received", "submitted", "on_hold"].includes(receipt.status)
        )
          continue;
        for (const item of receipt.items) {
          receivedByProduct.set(
            item.product,
            (receivedByProduct.get(item.product) ?? 0) + item.quantity_received,
          );
        }
      }
      return {
        order: {
          id: String(order.id),
          number: order.reference,
          status: toUiOrderStatus(order.status),
          notes: order.notes,
          currency: order.currency,
          exchange_rate: order.exchange_rate,
          exchange_rate_date: order.exchange_rate_date,
          reference_exchange_rate: order.reference_exchange_rate,
          exchange_rate_reason: order.exchange_rate_reason,
          exchange_rate_applied_at: order.exchange_rate_applied_at,
          exchange_rate_applied_by_name: order.exchange_rate_applied_by_name,
          created_at: order.order_date,
          received_at: order.status === "received" ? order.order_date : null,
          qr_token: null,
          suppliers: supplier
            ? {
                name: supplier.name,
                company_name: supplier.company_name,
                contact_name: supplier.contact_name,
                phone: supplier.phone,
                email: supplier.email,
                address: supplier.address,
              }
            : null,
        },
        items: order.items.map((item) => {
          const product = productById.get(item.product);
          return {
            id: String(item.id),
            product_id: item.product,
            quantity: item.quantity,
            received_quantity: receivedByProduct.get(item.product) ?? 0,
            unit_cost:
              item.unit_cost == null || !Number.isFinite(Number(item.unit_cost))
                ? null
                : Number(item.unit_cost),
            products: product ? { name: product.name, reference: product.sku } : null,
          };
        }),
        locations,
      };
    },
  });

  const items = data?.items ?? [];
  const order = data?.order;

  useEffect(() => {
    setReceived(Object.fromEntries(items.map((it) => [it.id, it.received_quantity])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const hasPrices = items.every((item) => item.unit_cost != null);
  const total = hasPrices
    ? items.reduce((sum, item) => sum + item.quantity * (item.unit_cost ?? 0), 0)
    : null;

  const setStatus = useMutation({
    mutationFn: async (status: string) => {
      if (status === "envoyee") {
        await api.post(`purchase-orders/${orderId}/send/`);
      } else if (status === "approved") {
        await api.post(`purchase-orders/${orderId}/confirm/`);
      } else {
        const reason = window.prompt(t("orders.cancelReason"));
        if (!reason?.trim()) throw new Error(t("receipts.reasonRequired"));
        await api.post(`purchase-orders/${orderId}/cancel/`, { reason });
      }
    },
    onSuccess: () => {
      toast.success(t("orders.statusUpdated"));
      void qc.invalidateQueries({ queryKey: ["purchase_order", orderId] });
      void qc.invalidateQueries({ queryKey: ["purchase_orders"] });
    },
    onError: (e: Error) => toast.error(t("orders.updateError"), { description: e.message }),
  });

  const receive = useMutation({
    mutationFn: async () => {
      const receiptItems = items.flatMap((item) => {
        const next = Math.max(
          0,
          Math.min(item.quantity, received[item.id] ?? item.received_quantity),
        );
        const quantityReceived = next - item.received_quantity;
        return quantityReceived > 0
          ? [
              {
                product: item.product_id,
                quantity_received: quantityReceived,
                ...(item.unit_cost == null ? {} : { unit_cost: item.unit_cost }),
              },
            ]
          : [];
      });
      if (!receiptItems.length) throw new Error(t("orders.receiveQuantityError"));

      if (!locationId) throw new Error(t("receipts.chooseLocation"));
      const receipt = await api.post<{ id: number }>("receipts/", {
        purchase_order: Number(orderId),
        location: Number(locationId),
        reference: `REC-${Date.now()}`,
        allocation_method: "quantity",
        items: receiptItems,
      });
      await api.post(`receipts/${receipt.id}/submit/`);
    },
    onSuccess: () => {
      toast.success(t("orders.receiptRecorded"), {
        description: t("orders.receiptSubmittedForReview"),
      });
      void qc.invalidateQueries({ queryKey: ["purchase_order", orderId] });
      void qc.invalidateQueries({ queryKey: ["purchase_orders"] });
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["movements"] });
    },
    onError: (e: Error) => toast.error(t("orders.receiptError"), { description: e.message }),
  });

  const emailOrder = useMutation({
    mutationFn: async () => {
      if (!order) throw new Error(t("orders.notFound"));
      const pdf = await buildOrderPdf();
      const formData = new FormData();
      formData.append("file", pdf, `${order.number}.pdf`);
      return api.post<{ detail: string; status: string }>(
        `purchase-orders/${orderId}/email/`,
        formData,
      );
    },
    onSuccess: () => {
      toast.success(t("orders.emailSent"));
      void qc.invalidateQueries({ queryKey: ["purchase_order", orderId] });
      void qc.invalidateQueries({ queryKey: ["purchase_orders"] });
    },
    onError: (error: Error) => toast.error(t("orders.emailError"), { description: error.message }),
  });

  if (isLoading) return <p className="text-muted-foreground text-sm">{t("invoice.loading")}</p>;

  if (!order) {
    return (
      <div className="panel mx-auto max-w-md p-6 text-center">
        <h1 className="text-lg font-semibold">{t("orders.notFound")}</h1>
        <Button asChild className="mt-4">
          <Link to="/commandes">{t("orders.back")}</Link>
        </Button>
      </div>
    );
  }

  function toUiOrderStatus(status: string) {
    if (status === "draft") return "brouillon";
    if (status === "received" || status === "closed") return "recue";
    if (status === "cancelled") return "annulee";
    if (status === "approved" || status === "partial_received") return status;
    return "envoyee";
  }

  function buildOrderPdf() {
    if (!order) throw new Error(t("orders.notFound"));
    return buildPurchaseOrderPdf({
      number: order.number,
      date: dateTime(order.created_at),
      status: t(
        order.status === "brouillon"
          ? "orders.status.draft"
          : order.status === "recue"
            ? "orders.status.received"
            : order.status === "annulee"
              ? "orders.status.cancelled"
              : order.status === "approved"
                ? "orders.status.approved"
                : order.status === "partial_received"
                  ? "orders.status.partial"
                  : "orders.status.submitted",
      ),
      currency: order.currency,
      supplier: {
        name: order.suppliers?.name ?? t("orders.supplierUndefined"),
        companyName: order.suppliers?.company_name,
        contactName: order.suppliers?.contact_name,
        phone: order.suppliers?.phone,
        email: order.suppliers?.email,
        address: order.suppliers?.address,
      },
      lines: items.map((item) => ({
        name: item.products?.name ?? "—",
        reference: item.products?.reference ?? "",
        quantity: item.quantity,
        unitCost: item.unit_cost,
      })),
      notes: order.notes,
      exchangeRate: order.exchange_rate,
      total,
    });
  }

  async function downloadOrderPdf() {
    try {
      const pdf = await buildOrderPdf();
      downloadPdfBlob(pdf, `${order.number}.pdf`);
    } catch (error) {
      toast.error(t("orders.pdfError"), {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async function previewOrderPdf(print = false) {
    try {
      const pdf = await buildOrderPdf();
      const url = URL.createObjectURL(pdf);
      const preview = window.open(url, "_blank");
      if (!preview) {
        URL.revokeObjectURL(url);
        throw new Error(t("orders.pdfPopupBlocked"));
      }
      preview.opener = null;
      if (print) {
        preview.addEventListener("load", () => preview.print(), { once: true });
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      toast.error(t("orders.pdfError"), {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async function shareOrder() {
    if (!order) return;
    try {
      const pdf = await buildOrderPdf();
      const result = await shareOnWhatsApp(
        pdf,
        `${order.number}.pdf`,
        t("orders.confirmationSent", { number: order.number, url: "" }),
        order.suppliers?.phone ?? undefined,
      );
      if (result === "downloaded") {
        toast.info(t("orders.pdfDownloaded"), { description: t("orders.pdfHint") });
      }
    } catch (error) {
      toast.error(t("orders.pdfError"), {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Button variant="outline" asChild>
        <Link to="/commandes">
          <ArrowLeft className="size-4" /> {t("orders.backShort")}
        </Link>
      </Button>

      <div className="panel space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3">
          <div>
            <h1 className="font-display text-xl font-bold uppercase">
              {t("orders.supplierOrder")} {order.number}
            </h1>
            <p className="text-muted-foreground text-xs">
              {order.suppliers?.name ?? t("orders.supplierUndefined")} ·{" "}
              {dateTime(order.created_at)}
            </p>
          </div>
          <Badge variant={statusVariant(order.status)}>
            {t(
              order.status === "brouillon"
                ? "orders.status.draft"
                : order.status === "recue"
                  ? "orders.status.received"
                  : order.status === "annulee"
                    ? "orders.status.cancelled"
                    : order.status === "approved"
                      ? "orders.status.approved"
                      : order.status === "partial_received"
                        ? "orders.status.partial"
                        : "orders.status.submitted",
            )}
          </Badge>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("orders.product")}</TableHead>
              <TableHead className="text-right">{t("orders.ordered")}</TableHead>
              <TableHead className="text-right">{t("orders.received")}</TableHead>
              <TableHead className="hidden text-right sm:table-cell">
                {t("orders.purchasePrice")}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((it) => (
              <TableRow key={it.id}>
                <TableCell>
                  <p className="font-medium">{it.products?.name ?? "—"}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {it.products?.reference}
                  </p>
                </TableCell>
                <TableCell className="text-right">{it.quantity}</TableCell>
                <TableCell className="text-right">
                  {manage ? (
                    <Input
                      type="number"
                      min={0}
                      max={it.quantity}
                      className="ml-auto w-20 text-right"
                      value={received[it.id] ?? it.received_quantity}
                      onChange={(e) =>
                        setReceived((prev) => ({ ...prev, [it.id]: Number(e.target.value) || 0 }))
                      }
                    />
                  ) : (
                    <span className={it.received_quantity < it.quantity ? "text-destructive" : ""}>
                      {it.received_quantity}
                    </span>
                  )}
                </TableCell>
                <TableCell className="hidden text-right sm:table-cell">
                  {money(it.unit_cost, order.currency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {total != null && (
          <p className="text-right text-sm font-bold">
            {t("orders.total")} : {money(total, order.currency)}
          </p>
        )}
        {order.currency !== "GNF" && (
          <div className="text-muted-foreground space-y-1 text-right text-xs">
            <p>
              {t("orders.exchangeRateReference")}: {order.reference_exchange_rate ?? "—"} GNF/USD
              {order.exchange_rate_date ? ` · ${order.exchange_rate_date}` : ""}
            </p>
            <p>
              {t("orders.exchangeRateApplied")}: {order.exchange_rate} GNF/USD
            </p>
            {order.exchange_rate_applied_at && (
              <p>
                {t("orders.exchangeRateAppliedDate")}: {dateTime(order.exchange_rate_applied_at)}
              </p>
            )}
            {order.exchange_rate_reason && (
              <p>
                {t("orders.exchangeRateReason")}: {order.exchange_rate_reason}
              </p>
            )}
            {order.exchange_rate_applied_by_name && (
              <p>
                {t("settings.exchangeRateBy")}: {order.exchange_rate_applied_by_name}
              </p>
            )}
            {Number(order.exchange_rate) > 0 && (
              <p>
                {t("orders.gnfEquivalent")}: {money(total * Number(order.exchange_rate))}
              </p>
            )}
          </div>
        )}
        {order.notes && (
          <p className="text-muted-foreground text-sm">
            {t("orders.note")} : {order.notes}
          </p>
        )}
        {order.received_at && (
          <p className="text-muted-foreground text-xs">
            {t("orders.receivedAt")} {dateTime(order.received_at)}
          </p>
        )}

        <div className="flex flex-wrap items-end justify-between gap-4 border-t pt-4">
          <div className="flex items-center gap-3">
            {order.qr_token && (
              <QrImage value={docQrValue(siteOrigin(), order.qr_token)} size={84} />
            )}
            <p className="text-muted-foreground max-w-[16rem] text-[11px]">
              {t("orders.verifyQr")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 print:hidden">
            <Button variant="outline" onClick={() => void shareOrder()}>
              <Share2 className="size-4" /> {t("orders.share")}
            </Button>
            <Button variant="outline" onClick={() => void previewOrderPdf()}>
              {t("orders.previewPdf")}
            </Button>
            <Button variant="outline" onClick={() => void downloadOrderPdf()}>
              <Download className="size-4" /> {t("orders.downloadPdf")}
            </Button>
            <Button variant="outline" onClick={() => void previewOrderPdf(true)}>
              <Printer className="size-4" /> {t("orders.print")}
            </Button>
            {manage && order.status === "brouillon" && (
              <Button
                onClick={() => emailOrder.mutate()}
                disabled={
                  emailOrder.isPending ||
                  !order.suppliers?.email ||
                  !hasPrices ||
                  items.length === 0
                }
              >
                <Mail className="size-4" />
                {emailOrder.isPending ? t("orders.emailSending") : t("orders.emailSupplier")}
              </Button>
            )}
          </div>
        </div>
        {manage && order.status === "brouillon" && !order.suppliers?.email && (
          <p className="text-muted-foreground text-right text-xs">
            {t("orders.supplierEmailMissing")}
          </p>
        )}
        {manage &&
          order.status === "brouillon" &&
          order.suppliers?.email &&
          (!hasPrices || items.length === 0) && (
            <p className="text-muted-foreground text-right text-xs">
              {t("orders.emailRequirements")}
            </p>
          )}
        <PartnerStrip surface="orders" className="print:flex" />

        {manage && (
          <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
            <div className="min-w-56 space-y-1">
              <p className="text-muted-foreground text-xs">{t("receipts.storageLocation")}</p>
              <Select value={locationId} onValueChange={setLocationId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("receipts.chooseLocation")} />
                </SelectTrigger>
                <SelectContent>
                  {data?.locations
                    .filter((location) => location.location_type !== "other")
                    .map((location) => (
                      <SelectItem key={location.id} value={String(location.id)}>
                        {location.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            {order.status === "brouillon" && (
              <Button variant="outline" onClick={() => setStatus.mutate("envoyee")}>
                {t("orders.markSent")}
              </Button>
            )}
            {hasRole("admin") && order.status === "envoyee" && (
              <Button onClick={() => setStatus.mutate("approved")}>{t("orders.approve")}</Button>
            )}
            {hasRole("admin") && order.status !== "annulee" && order.status !== "recue" && (
              <Button variant="ghost" onClick={() => setStatus.mutate("annulee")}>
                {t("orders.cancelOrder")}
              </Button>
            )}
            {["approved", "partial_received"].includes(order.status) && (
              <Button onClick={() => receive.mutate()} disabled={receive.isPending || !locationId}>
                {t("orders.receiveGoods")}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
