import { Route as FileRoute } from "@/routes/_authenticated/livraisons/$deliveryId";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CompanyHeader } from "@/components/CompanyHeader";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Printer, Share2, Truck } from "lucide-react";
import { toast } from "sonner";

import { PartnerStrip } from "@/components/PartnerStrip";
import { RequirePermission } from "@/components/RequirePermission";
import { brandLogo } from "@/lib/brand-assets";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { buildDocumentPdf, shareOnWhatsApp } from "@/lib/document-pdf";
import { dateTime } from "@/lib/format";
import { useLocale } from "@/lib/locale";
import { QrImage } from "@/lib/qr";

export const PageRoute = createFileRoute("/_authenticated/livraisons/$deliveryId")({
  head: () => ({
    meta: [
      { title: "Bon de livraison — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Bon de livraison imprimable avec QR code de vérification, lignes livrées et partage WhatsApp.",
      },
      { property: "og:title", content: "Bon de livraison — DJIBEXA" },
      {
        property: "og:description",
        content: "Document de livraison officiel avec QR code d'authenticité.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="deliveries.view">
      <BonLivraison />
    </RequirePermission>
  ),
});

const STATUS_KEYS: Record<string, string> = {
  prepared: "delivery.prepared",
  delivered: "delivery.delivered",
  cancelled: "delivery.cancelled",
};

function deliveryStatusLabel(status: string, t: (key: string) => string) {
  const key = STATUS_KEYS[status];
  return key ? t(key) : status;
}

function BonLivraison() {
  const { deliveryId } = FileRoute.useParams();
  const { t } = useLocale();
  const qc = useQueryClient();
  const { can } = useAuth();

  const { data: note } = useQuery({
    queryKey: ["delivery-note", deliveryId],
    queryFn: () =>
      api.get<{
        id: number;
        reference: string;
        status: string;
        notes: string;
        created_at: string;
        customer_name: string;
        customer_phone: string;
        customer_address: string;
        sale_reference: string;
        verification_url: string;
        items: { id: number; product_name: string; product_sku: string; quantity: number }[];
      }>(`documents/delivery-notes/${deliveryId}/`),
  });
  const items = note?.items ?? [];

  const markDelivered = useMutation({
    mutationFn: async () => {
      await api.patch(`documents/delivery-notes/${deliveryId}/`, { status: "delivered" });
    },
    onSuccess: () => {
      toast.success(t("delivery.markedDelivered"));
      void qc.invalidateQueries({ queryKey: ["delivery-note", deliveryId] });
      void qc.invalidateQueries({ queryKey: ["delivery-notes"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const verifyUrl = note?.verification_url ?? "";

  async function share() {
    if (!note) return;
    const pdf = await buildDocumentPdf({
      kind: t("delivery.title"),
      number: note.reference,
      date: dateTime(note.created_at),
      parties: [
        { label: t("delivery.customer"), value: note.customer_name ?? t("sales.customerCounter") },
        { label: t("credits.phone"), value: note.customer_phone ?? "-" },
        { label: t("delivery.sale"), value: note.sale_reference ?? "-" },
      ],
      lines: (items ?? []).map((i) => ({
        label: i.product_name,
        sub: i.product_sku,
        qty: i.quantity,
      })),
      verifyUrl,
      footer: t("delivery.verify"),
    });
    const result = await shareOnWhatsApp(
      pdf,
      `${note.reference}.pdf`,
      `${t("delivery.title")} ${note.reference} — DJIBEXA. ${t("delivery.verify")} ${verifyUrl}`,
      note.customer_phone ?? undefined,
    );
    if (result === "downloaded") {
      toast.info(t("delivery.pdfDownloaded"), { description: t("delivery.pdfHint") });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link to="/livraisons">
            <ArrowLeft className="size-4" /> {t("delivery.title")}
          </Link>
        </Button>
        <div className="flex flex-wrap gap-2">
          {note?.status === "prepared" && can("deliveries.manage") && (
            <Button variant="outline" onClick={() => markDelivered.mutate()}>
              <Truck className="size-4" /> {t("delivery.markDelivered")}
            </Button>
          )}
          <Button variant="outline" onClick={() => void share()}>
            <Share2 className="size-4" /> {t("delivery.share")}
          </Button>
          <Button onClick={() => window.print()}>
            <Printer className="size-4" /> {t("delivery.print")}
          </Button>
        </div>
      </div>

      <div className="panel mx-auto w-full max-w-3xl space-y-5 p-6 print:border-0 print:shadow-none">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={brandLogo} alt={t("landing.logoAlt")} className="h-14 w-40 object-contain" />
            <CompanyHeader size="lg" />
          </div>
          <div className="text-right">
            <p className="font-bold uppercase">{t("delivery.title")}</p>
            <p className="font-mono text-sm">{note?.reference}</p>
            <p className="text-muted-foreground text-xs">{note ? dateTime(note.created_at) : ""}</p>
            <Badge
              className="mt-1"
              variant={note?.status === "delivered" ? "default" : "secondary"}
            >
              {note ? deliveryStatusLabel(note.status, t) : ""}
            </Badge>
          </div>
        </div>

        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-muted-foreground text-xs uppercase">{t("delivery.customer")}</p>
            <p className="font-medium">{note?.customer_name ?? t("sales.customerCounter")}</p>
            <p className="text-muted-foreground text-xs">{note?.customer_phone ?? ""}</p>
            <p className="text-muted-foreground text-xs">{note?.customer_address ?? ""}</p>
          </div>
          <div className="sm:text-right">
            <p className="text-muted-foreground text-xs uppercase">{t("delivery.linkedSale")}</p>
            <p className="font-mono">{note?.sale_reference ?? "—"}</p>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("delivery.designation")}</TableHead>
              <TableHead className="text-right">{t("delivery.quantity")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(items ?? []).map((i) => (
              <TableRow key={i.id}>
                <TableCell>
                  <p className="font-medium">{i.product_name}</p>
                  <p className="text-muted-foreground font-mono text-xs">{i.product_sku}</p>
                </TableCell>
                <TableCell className="text-right">{i.quantity}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {note?.notes && <p className="text-muted-foreground text-xs">{note.notes}</p>}

        <div className="flex flex-wrap items-end justify-between gap-4 border-t pt-4">
          <div className="flex items-center gap-3">
            {verifyUrl && <QrImage value={verifyUrl} size={88} />}
            <p className="text-muted-foreground max-w-[180px] text-[10px]">
              {t("delivery.verify")}
            </p>
          </div>
          <PartnerStrip surface="invoice" />
        </div>

        <div className="grid grid-cols-2 gap-8 pt-6 text-xs">
          <div className="border-t pt-1 text-center">{t("delivery.storeSignature")}</div>
          <div className="border-t pt-1 text-center">{t("delivery.customerSignature")}</div>
        </div>
      </div>
    </div>
  );
}
