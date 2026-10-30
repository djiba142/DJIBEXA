import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CompanyFooter } from "@/components/CompanyHeader";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Download, Printer, RotateCcw, Share2 } from "lucide-react";
import { toast } from "sonner";

import { PartnerStrip } from "@/components/PartnerStrip";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { shareOnWhatsApp } from "@/lib/document-pdf";
import { dateTime, money, numberToFrenchWords } from "@/lib/format";
import { useLocale } from "@/lib/locale";
import { QrImage } from "@/lib/qr";
import { useSettings } from "@/lib/settings";
import { useState } from "react";

import { Route as FileRoute } from "@/routes/_authenticated/ventes/$saleId";

export const PageRoute = createFileRoute("/_authenticated/ventes/$saleId")({
  head: () => ({
    meta: [
      { title: "Facture — DJIBEXA" },
      {
        name: "description",
        content: "Facture détaillée imprimable : lignes de vente, paiements et solde en GNF.",
      },
      { property: "og:title", content: "Facture — DJIBEXA" },
      {
        property: "og:description",
        content: "Facture commerciale de KOUROUMA AUTO PARTS dans DJIBEXA ERP.",
      },
    ],
  }),
  component: FacturePage,
});

function FacturePage() {
  const { saleId } = FileRoute.useParams();
  const { t } = useLocale();
  const { hasRole } = useAuth();
  const settings = useSettings();
  const queryClient = useQueryClient();
  const [returnOpen, setReturnOpen] = useState(false);
  const [returnReason, setReturnReason] = useState("");
  const [returnQuantities, setReturnQuantities] = useState<Record<number, string>>({});
  const [returnRestockQuantities, setReturnRestockQuantities] = useState<Record<number, string>>(
    {},
  );
  const [releaseQuantities, setReleaseQuantities] = useState<Record<number, string>>({});
  const [releaseReasons, setReleaseReasons] = useState<Record<number, string>>({});
  const [signatureRetry, setSignatureRetry] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["facture", saleId],
    queryFn: async () => {
      const sale = await api.get<{
        id: number;
        customer: number | null;
        customer_name: string;
        seller_name: string;
        invoice_number: string | null;
        invoice_qr_code: string | null;
        total_amount: string;
        amount_paid: string;
        discount: string;
        payment_method: string;
        created_at: string;
        status: string;
        items: {
          id: number;
          quantity: number;
          unit_price: string;
          product_name: string;
          product_sku: string;
        }[];
      }>(`sales/${saleId}/`);
      const [customer, invoices, branding] = await Promise.all([
        sale.customer
          ? api.get<{ full_name: string; phone: string; address: string }>(
              `customers/${sale.customer}/`,
            )
          : Promise.resolve(null),
        api.list<{
          id: number;
          sale_id: number;
          verification_url: string;
          document_status: string;
          document_pages: number;
        }>("invoices/"),
        api.get<{
          company_name: string;
          activity: string;
          distributor_details: string;
          address: string;
          phone_numbers: string[];
          email_addresses: string[];
          rccm: string;
          nif: string;
          additional_lines: string[];
          line_display_mode: "compact" | "carnet";
          header_alignment: "left" | "center";
          header_color: string;
          text_color: string;
          show_company_name: boolean;
          show_activity: boolean;
          show_distributor: boolean;
          show_address: boolean;
          show_phones: boolean;
          show_emails: boolean;
          show_logo: boolean;
          show_automotive_image: boolean;
          show_watermark: boolean;
          show_stamp: boolean;
          show_qr: boolean;
          logo_url: string;
          automotive_image_url: string;
          watermark_image_url: string;
          stamp_image_url: string;
          stamp_size_mm: number;
          stamp_opacity: number;
        }>("invoices/branding/"),
      ]);
      const invoice = invoices.find((item) => item.sale_id === sale.id);
      return {
        sale,
        customer,
        items: sale.items,
        sellerName: sale.seller_name,
        invoiceId: invoice?.id,
        documentStatus: invoice?.document_status ?? "unissued",
        documentPages: invoice?.document_pages ?? 0,
        verificationUrl: invoice?.verification_url ?? "",
        branding,
      };
    },
  });

  const sale = data?.sale;
  const items = data?.items ?? [];
  const subtotal = items.reduce((s, it) => s + it.quantity * Number(it.unit_price), 0);
  const discount = Number(sale?.discount ?? 0);
  const amountPaid = Number(sale?.amount_paid ?? 0);
  const balanceDue = Math.max(0, Number(sale?.total_amount ?? 0) - amountPaid);
  const invoiceNumber = sale?.invoice_number ?? `VTE-${sale?.id ?? saleId}`;
  const invoicePages = Array.from(
    { length: Math.max(1, Math.ceil(items.length / 25)) },
    (_, pageIndex) => items.slice(pageIndex * 25, (pageIndex + 1) * 25),
  );
  const lineDisplayMode = data?.branding.line_display_mode ?? settings.invoiceLineDisplayMode;
  const cancelled = sale?.status === "cancelled";
  const paymentMethod = sale?.payment_method.trim().toLowerCase().replaceAll(" ", "_");
  const paymentLabel =
    paymentMethod === "cash"
      ? t("sales.cash")
      : paymentMethod === "mobile_money"
        ? t("sales.mobileMoney")
        : paymentMethod === "credit"
          ? t("sales.credit")
          : sale?.payment_method;
  const canRegisterReturn = hasRole("admin");
  const quarantinesQuery = useQuery({
    queryKey: ["sale-return-quarantines", saleId],
    queryFn: () =>
      api.list<{
        id: number;
        product_name: string;
        location_name: string;
        quantity_remaining: number;
        reason: string;
      }>(`sales/${saleId}/returns/quarantines/`),
    enabled: hasRole("admin"),
  });
  const returnMutation = useMutation({
    mutationFn: () => {
      const returnedItems = items
        .map((item) => {
          const quantity = Number(returnQuantities[item.id] || 0);
          const restockQuantity = Number(returnRestockQuantities[item.id] || 0);
          return {
            sale_item: item.id,
            quantity,
            restock_quantity: restockQuantity,
            quarantined_quantity: quantity - restockQuantity,
            quarantine_reason: returnReason,
          };
        })
        .filter((item) => item.quantity > 0);
      if (!returnedItems.length) throw new Error(t("invoice.returnQuantityRequired"));
      if (
        returnedItems.some(
          (item) =>
            item.restock_quantity > item.quantity ||
            (item.quarantined_quantity > 0 && !returnReason.trim()),
        )
      ) {
        throw new Error(t("invoice.quarantineReasonRequired"));
      }
      return api.post<{ returned_amount: string }>(`sales/${saleId}/returns/`, {
        reason: returnReason,
        items: returnedItems,
      });
    },
    onSuccess: async () => {
      toast.success(t("invoice.returnRegistered"));
      setReturnOpen(false);
      setReturnReason("");
      setReturnQuantities({});
      setReturnRestockQuantities({});
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["rapports"] }),
        queryClient.invalidateQueries({ queryKey: ["sales"] }),
        queryClient.invalidateQueries({ queryKey: ["sale-return-quarantines", saleId] }),
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : t("invoice.returnFailed"));
    },
  });
  const releaseQuarantineMutation = useMutation({
    mutationFn: ({
      quarantineId,
      quantity,
      reason,
    }: {
      quarantineId: number;
      quantity: number;
      reason: string;
    }) =>
      api.post(`sales/return-quarantines/${quarantineId}/release/`, {
        quantity,
        reason,
      }),
    onSuccess: async () => {
      toast.success(t("invoice.quarantineReleased"));
      setReleaseQuantities({});
      setReleaseReasons({});
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sale-return-quarantines", saleId] }),
        queryClient.invalidateQueries({ queryKey: ["stock"] }),
        queryClient.invalidateQueries({ queryKey: ["rapports"] }),
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : t("invoice.quarantineReleaseFailed"));
    },
  });

  if (isLoading) {
    return <p className="text-muted-foreground text-sm">{t("invoice.loading")}</p>;
  }

  if (!sale) {
    return (
      <div className="panel mx-auto max-w-md p-6 text-center">
        <h1 className="text-lg font-semibold">{t("invoice.notFound")}</h1>
        <Button asChild className="mt-4">
          <Link to="/ventes">{t("invoice.back")}</Link>
        </Button>
      </div>
    );
  }

  const invoiceWarnings = [
    items.length === 0 ? t("invoice.incompleteItemsWarning") : "",
    settings.printQrOnDocs && !data?.verificationUrl ? t("invoice.missingVerificationWarning") : "",
    !data?.sellerName?.trim() ? t("invoice.missingSellerWarning") : "",
  ].filter(Boolean);
  const invoiceReady = invoiceWarnings.length === 0;

  function amountInWords() {
    const amount = numberToFrenchWords(Math.round(Number(sale?.total_amount ?? 0)));
    return t("invoice.amountInWords", { amount: `${amount} francs guinéens` });
  }

  async function issueInvoiceDocument() {
    if (!invoiceReady) {
      toast.error(invoiceWarnings[0]);
      return false;
    }
    if (!data?.invoiceId) {
      toast.error("La facture serveur associée à cette vente est introuvable.");
      return false;
    }
    try {
      const result = await api.post<{ document_status: string }>(
        `invoices/${data.invoiceId}/issue/`,
        signatureRetry ? { retry: true } : {},
      );
      if (result.document_status !== "signed") {
        throw new Error("Le PDF n’a pas été signé et vérifié.");
      }
      setSignatureRetry(false);
      await queryClient.invalidateQueries({ queryKey: ["facture", saleId] });
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.status === 503) setSignatureRetry(true);
      toast.error(error instanceof Error ? error.message : "Émission du PDF impossible.");
      return false;
    }
  }

  async function downloadInvoice() {
    if (!(await issueInvoiceDocument())) return;
    await api.download(`invoices/${data?.invoiceId}/pdf/`, `${invoiceNumber}.pdf`);
    toast.success(t("invoice.pdfDownloaded"));
  }

  async function shareInvoice() {
    if (!sale || !(await issueInvoiceDocument())) return;
    const pdf = await api.blob(`invoices/${data?.invoiceId}/pdf/`);
    const verifyUrl = data?.verificationUrl ?? "";
    const result = await shareOnWhatsApp(
      pdf,
      `${invoiceNumber}.pdf`,
      t("invoice.confirmationSent", {
        number: sale.invoice_number ?? `VTE-${sale.id}`,
        url: verifyUrl,
      }),
      data?.customer?.phone ?? undefined,
    );
    if (result === "downloaded") {
      toast.info(t("invoice.pdfDownloaded"), { description: t("invoice.pdfHint") });
    }
  }

  return (
    <>
      <style>{`@media print { @page { size: A4 portrait; margin: 8mm; } }`}</style>
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
          <Button variant="outline" asChild>
            <Link to="/ventes">
              <ArrowLeft className="size-4" /> {t("invoice.back")}
            </Link>
          </Button>
          <div className="flex flex-wrap gap-2">
            {canRegisterReturn && items.length > 0 && !cancelled && sale.status !== "draft" && (
              <Button variant="outline" onClick={() => setReturnOpen(true)}>
                <RotateCcw className="size-4" /> {t("invoice.registerReturn")}
              </Button>
            )}
            <Button variant="outline" disabled={!invoiceReady} onClick={() => void shareInvoice()}>
              <Share2 className="size-4" /> {t("invoice.share")}
            </Button>
            <Button
              variant="outline"
              disabled={!invoiceReady}
              onClick={() => void downloadInvoice()}
            >
              <Download className="size-4" />{" "}
              {signatureRetry ? "Réessayer la signature" : t("invoice.downloadPdf")}
            </Button>
            <Button
              disabled={!invoiceReady || data?.documentStatus !== "signed"}
              onClick={() => window.print()}
            >
              <Printer className="size-4" /> {t("invoice.print")}
            </Button>
          </div>
        </div>

        {invoiceWarnings.length > 0 && (
          <div
            className="border-destructive/40 bg-destructive/5 text-destructive rounded-lg border p-4 text-sm print:hidden"
            role="alert"
          >
            <p className="font-semibold">{t("invoice.exportBlocked")}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {invoiceWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        {invoicePages.map((pageItems, pageIndex) => {
          const invoiceRows =
            lineDisplayMode === "carnet"
              ? Array.from({ length: 25 }, (_, index) => pageItems[index])
              : pageItems;
          const isFinalPage = pageIndex === invoicePages.length - 1;
          return (
            <div
              key={pageIndex}
              className={`panel invoice-print-sheet space-y-3 p-4 print:border-0 print:shadow-none sm:p-6 ${!isFinalPage ? "invoice-page-break" : ""}`}
            >
              <header
                className="-mx-4 -mt-4 flex flex-wrap items-start justify-between gap-4 rounded-t-md px-4 py-4 sm:-mx-6 sm:-mt-6 sm:px-6 print:rounded-none"
                style={{
                  backgroundColor: data?.branding.header_color ?? settings.invoiceHeaderColor,
                  color: data?.branding.text_color ?? settings.invoiceTextColor,
                }}
              >
                <div className="flex min-w-0 items-center gap-3">
                  {(data?.branding.show_logo ?? true) && data?.branding.logo_url ? (
                    <img
                      src={data.branding.logo_url}
                      alt="Logo de la facture"
                      className="h-12 w-14 shrink-0 object-contain"
                    />
                  ) : (data?.branding.show_logo ?? true) ? (
                    <span className="grid size-12 shrink-0 place-items-center rounded bg-white font-display text-sm font-bold text-primary">
                      KAP
                    </span>
                  ) : null}
                  <div className="min-w-0 flex-1 text-center">
                    {(data?.branding.show_company_name ?? true) && (
                      <p className="font-display text-base font-bold uppercase">
                        {data?.branding.company_name ?? settings.companyName}
                      </p>
                    )}
                    {(data?.branding.show_activity ?? true) && (
                      <p className="text-xs opacity-80">
                        {data?.branding.activity ?? settings.slogan}
                      </p>
                    )}
                    {(data?.branding.show_distributor ?? true) && (
                      <p className="text-xs opacity-80">
                        {data?.branding.distributor_details ?? settings.distributorDetails}
                      </p>
                    )}
                    {(data?.branding.show_address ?? true) &&
                      data?.branding.address &&
                      !data.branding.distributor_details.includes(data.branding.address) && (
                        <p className="text-xs opacity-80">{data.branding.address}</p>
                      )}
                    {(data?.branding.show_phones ?? true) &&
                      (data?.branding.phone_numbers ?? settings.phoneNumbers).map((phone) => (
                        <p key={phone} className="text-xs opacity-80">
                          Tél. {phone}
                        </p>
                      ))}
                    {(data?.branding.show_emails ?? true) &&
                      (data?.branding.email_addresses ?? settings.emailAddresses).map((email) => (
                        <p key={email} className="text-xs opacity-80">
                          {email}
                        </p>
                      ))}
                    {(data?.branding.additional_lines ?? settings.additionalInvoiceLines).map(
                      (line, index) => (
                        <p key={`${index}-${line}`} className="text-xs opacity-80">
                          {line}
                        </p>
                      ),
                    )}
                  </div>
                  {(data?.branding.show_automotive_image ?? true) &&
                    data?.branding.automotive_image_url && (
                      <img
                        src={data.branding.automotive_image_url}
                        alt="Illustration automobile"
                        className="hidden h-16 w-24 shrink-0 object-contain md:block"
                      />
                    )}
                </div>
                <div className="text-right">
                  <p className="font-display text-lg font-bold uppercase">{t("invoice.title")}</p>
                  <p className="font-mono text-sm">{invoiceNumber}</p>
                  <p className="text-primary-foreground/80 text-xs">{dateTime(sale.created_at)}</p>
                  {invoicePages.length > 1 && (
                    <p className="text-primary-foreground/80 text-xs">
                      Page {pageIndex + 1}/{invoicePages.length}
                    </p>
                  )}
                  {cancelled && (
                    <p className="border-destructive text-destructive mt-2 inline-block rounded border-2 px-2 py-0.5 text-sm font-bold tracking-widest uppercase">
                      {t("invoice.cancelled")}
                    </p>
                  )}
                </div>
              </header>

              <section className="grid gap-4 text-sm sm:grid-cols-2">
                <div>
                  <p className="text-muted-foreground text-xs tracking-widest uppercase">
                    {t("invoice.customer")}
                  </p>
                  <p className="font-medium">{data?.customer?.full_name ?? t("invoice.walkIn")}</p>
                  {data?.customer?.phone && <p className="text-xs">{data.customer.phone}</p>}
                  {data?.customer?.address && <p className="text-xs">{data.customer.address}</p>}
                </div>
                <div className="sm:text-right">
                  <p className="text-muted-foreground text-xs tracking-widest uppercase">
                    {t("invoice.seller")}
                  </p>
                  <p className="font-medium">{data?.sellerName || "—"}</p>
                  <p className="text-xs capitalize">
                    {t("invoice.payment")} : {paymentLabel}
                  </p>
                </div>
              </section>

              <table className="w-full border-collapse border border-primary/50 text-xs">
                <thead>
                  <tr
                    className="border-y-2 text-left"
                    style={{
                      backgroundColor: data?.branding.header_color ?? settings.invoiceHeaderColor,
                      color: data?.branding.text_color ?? settings.invoiceTextColor,
                    }}
                  >
                    <th className="w-10 border-r border-primary-foreground/30 py-1 pl-2">
                      {t("invoice.lineNumber")}
                    </th>
                    <th className="border-r border-primary-foreground/30 py-1">
                      {t("invoice.designation")}
                    </th>
                    <th className="w-12 border-r border-primary-foreground/30 py-1 text-right">
                      {t("invoice.quantity")}
                    </th>
                    <th className="w-28 border-r border-primary-foreground/30 py-1 text-right">
                      {t("invoice.unitPrice")}
                    </th>
                    <th className="w-32 py-1 pr-2 text-right">{t("invoice.amount")}</th>
                  </tr>
                </thead>
                <tbody>
                  {invoiceRows.map((it, index) => (
                    <tr key={it?.id ?? `blank-${index}`} className="h-5 border-b border-primary/30">
                      <td className="border-r border-primary/30 py-0 pl-2 text-muted-foreground">
                        {pageIndex * 25 + index + 1}
                      </td>
                      <td className="max-w-0 border-r border-primary/30 py-0">
                        {it && (
                          <span className="block truncate font-medium">
                            {it.product_name}{" "}
                            <span className="text-muted-foreground">{it.product_sku}</span>
                          </span>
                        )}
                      </td>
                      <td className="border-r border-primary/30 py-0 text-right">
                        {it?.quantity ?? ""}
                      </td>
                      <td className="border-r border-primary/30 py-0 text-right">
                        {it ? money(Number(it.unit_price)) : ""}
                      </td>
                      <td className="py-0 pr-2 text-right font-medium">
                        {it ? money(it.quantity * Number(it.unit_price)) : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {isFinalPage && (
                <>
                  <div className="ml-auto w-full max-w-xs space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">{t("invoice.subtotal")}</span>
                      <span>{items.length ? money(subtotal) : "—"}</span>
                    </div>
                    {discount > 0 && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">{t("invoice.discount")}</span>
                        <span>-{money(discount)}</span>
                      </div>
                    )}
                    <div className="flex justify-between border-t pt-1 text-base font-bold">
                      <span>{t("invoice.total")}</span>
                      <span>{items.length ? money(Number(sale.total_amount)) : "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">{t("invoice.paid")}</span>
                      <span>{money(amountPaid)}</span>
                    </div>
                    <div className="flex justify-between font-semibold">
                      <span>{t("invoice.balanceDue")}</span>
                      <span>{money(balanceDue)}</span>
                    </div>
                  </div>

                  {items.length > 0 && (
                    <p className="border-t border-dotted pt-2 text-sm">{amountInWords()}</p>
                  )}

                  <div className="grid gap-5 border-t pt-4 sm:grid-cols-3">
                    <div className="flex items-center gap-3">
                      {(data?.branding.show_qr ?? settings.invoiceShowQr) &&
                        data?.verificationUrl && (
                          <QrImage
                            value={data.verificationUrl}
                            size={84}
                            alt={t("invoice.qrAlt", { number: invoiceNumber })}
                          />
                        )}
                      {(data?.branding.show_qr ?? settings.invoiceShowQr) &&
                        data?.verificationUrl && (
                          <p className="text-muted-foreground max-w-[16rem] text-[11px]">
                            {t("invoice.verify")}
                          </p>
                        )}
                    </div>

                    <div className="flex flex-col justify-center border-t pt-3 text-center text-xs sm:border-l sm:border-t-0 sm:pt-0">
                      <p className="text-muted-foreground uppercase">{t("invoice.issuedBy")}</p>
                      <p className="mt-3 font-display text-lg font-semibold italic">
                        {data?.sellerName || "—"}
                      </p>
                      <p className="border-t pt-1">{t("invoice.seller")}</p>
                      <p className="text-muted-foreground">{dateTime(sale.created_at)}</p>
                    </div>

                    {(data?.branding.show_stamp ?? settings.invoiceShowStamp) && (
                      <div className="flex justify-center border-t pt-3 sm:border-l sm:border-t-0 sm:pt-0">
                        {data?.branding.stamp_image_url ? (
                          <img
                            src={data.branding.stamp_image_url}
                            alt={t("invoice.professionalStamp")}
                            className="aspect-square object-contain"
                            style={{
                              width: `${(data.branding.stamp_size_mm * 96) / 25.4}px`,
                              opacity: data.branding.stamp_opacity / 100,
                            }}
                          />
                        ) : (
                          <div
                            className="flex aspect-square flex-col items-center justify-center rounded-full border-[3px] border-double px-2 text-center"
                            style={{
                              width: `${((data?.branding.stamp_size_mm ?? settings.invoiceStampSizeMm) * 96) / 25.4}px`,
                              opacity:
                                (data?.branding.stamp_opacity ?? settings.invoiceStampOpacity) /
                                100,
                              borderColor:
                                sale.status === "cancelled"
                                  ? "#b42318"
                                  : (data?.branding.header_color ?? settings.invoiceHeaderColor),
                              color:
                                sale.status === "cancelled"
                                  ? "#b42318"
                                  : (data?.branding.header_color ?? settings.invoiceHeaderColor),
                            }}
                          >
                            <span className="line-clamp-2 max-w-full text-[7px] leading-tight font-bold uppercase">
                              {data?.branding.company_name ?? settings.companyName}
                            </span>
                            <span
                              className="my-1 w-full truncate px-1 py-1 text-[9px] leading-none font-black tracking-wide text-white uppercase"
                              style={{
                                backgroundColor:
                                  sale.status === "cancelled"
                                    ? "#b42318"
                                    : (data?.branding.header_color ?? settings.invoiceHeaderColor),
                              }}
                            >
                              {sale.status === "cancelled" ? "Annulée" : "Validée"}
                            </span>
                            <span className="text-[6px] leading-none font-bold tracking-widest uppercase">
                              Facture
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <PartnerStrip surface="invoice" />

                  <footer className="text-muted-foreground border-t pt-3 text-center text-xs">
                    <CompanyFooter />
                  </footer>
                </>
              )}
            </div>
          );
        })}
        {hasRole("admin") && (
          <section className="panel mx-auto mt-4 w-full max-w-4xl space-y-3 p-4">
            <h2 className="font-semibold">{t("invoice.quarantineReview")}</h2>
            {quarantinesQuery.isLoading ? (
              <p className="text-muted-foreground text-sm">{t("invoice.loading")}</p>
            ) : (quarantinesQuery.data ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("invoice.noQuarantine")}</p>
            ) : (
              <div className="space-y-3">
                {quarantinesQuery.data?.map((quarantine) => (
                  <div key={quarantine.id} className="space-y-3 rounded-lg border p-3">
                    <div>
                      <p className="font-medium">{quarantine.product_name}</p>
                      <p className="text-muted-foreground text-sm">
                        {quarantine.location_name} · {t("invoice.quarantinePending")}:{" "}
                        {quarantine.quantity_remaining}
                      </p>
                      <p className="text-sm">{quarantine.reason}</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Input
                        type="number"
                        min="1"
                        max={quarantine.quantity_remaining}
                        placeholder={t("invoice.quarantineReleaseQuantity")}
                        value={releaseQuantities[quarantine.id] ?? ""}
                        onChange={(event) =>
                          setReleaseQuantities((current) => ({
                            ...current,
                            [quarantine.id]: event.target.value,
                          }))
                        }
                        aria-label={`${t("invoice.quarantineReleaseQuantity")} ${quarantine.product_name}`}
                      />
                      <Input
                        placeholder={t("invoice.quarantineReleaseReason")}
                        value={releaseReasons[quarantine.id] ?? ""}
                        onChange={(event) =>
                          setReleaseReasons((current) => ({
                            ...current,
                            [quarantine.id]: event.target.value,
                          }))
                        }
                        aria-label={`${t("invoice.quarantineReleaseReason")} ${quarantine.product_name}`}
                      />
                    </div>
                    <Button
                      onClick={() =>
                        releaseQuarantineMutation.mutate({
                          quarantineId: quarantine.id,
                          quantity: Number(releaseQuantities[quarantine.id] || 0),
                          reason: releaseReasons[quarantine.id] ?? "",
                        })
                      }
                      disabled={
                        releaseQuarantineMutation.isPending ||
                        !Number(releaseQuantities[quarantine.id]) ||
                        !releaseReasons[quarantine.id]?.trim()
                      }
                    >
                      {t("invoice.quarantineRelease")}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
        <Dialog open={returnOpen} onOpenChange={setReturnOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("invoice.returnTitle")}</DialogTitle>
            </DialogHeader>
            <p className="text-muted-foreground text-sm">{t("invoice.returnRefundSeparate")}</p>
            <div className="space-y-3">
              {items.map((item) => (
                <div key={item.id} className="space-y-2 text-sm">
                  <p>
                    {item.product_name} · {t("invoice.quantity")}: {item.quantity}
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="space-y-1">
                      <span className="text-muted-foreground text-xs">
                        {t("invoice.returnQuantity")}
                      </span>
                      <Input
                        type="number"
                        min="0"
                        max={item.quantity}
                        value={returnQuantities[item.id] ?? ""}
                        onChange={(event) =>
                          setReturnQuantities((current) => ({
                            ...current,
                            [item.id]: event.target.value,
                          }))
                        }
                        aria-label={`${t("invoice.returnQuantity")} ${item.product_name}`}
                      />
                    </label>
                    <label className="space-y-1">
                      <span className="text-muted-foreground text-xs">
                        {t("invoice.restockQuantity")}
                      </span>
                      <Input
                        type="number"
                        min="0"
                        max={returnQuantities[item.id] || item.quantity}
                        value={returnRestockQuantities[item.id] ?? ""}
                        onChange={(event) =>
                          setReturnRestockQuantities((current) => ({
                            ...current,
                            [item.id]: event.target.value,
                          }))
                        }
                        aria-label={`${t("invoice.restockQuantity")} ${item.product_name}`}
                      />
                    </label>
                  </div>
                </div>
              ))}
              <p className="text-muted-foreground text-xs">{t("invoice.quarantineHint")}</p>
              <Input
                value={returnReason}
                onChange={(event) => setReturnReason(event.target.value)}
                placeholder={t("invoice.returnReason")}
              />
            </div>
            <Button onClick={() => returnMutation.mutate()} disabled={returnMutation.isPending}>
              {returnMutation.isPending ? t("invoice.returnSaving") : t("invoice.registerReturn")}
            </Button>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
