import { Route as FileRoute } from "@/routes/verifier.$token";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { BadgeCheck, ShieldAlert } from "lucide-react";
import { useEffect } from "react";

import { PartnerStrip } from "@/components/PartnerStrip";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/verifier/$token")({
  head: () => ({
    meta: [
      { title: "Vérifier un document — DJIBEXA" },
      {
        name: "description",
        content:
          "Vérifiez l'authenticité d'une facture, d'un bon de commande ou d'un bon de livraison KOUROUMA AUTO PART.",
      },
      { property: "og:title", content: "Vérification de document — DJIBEXA" },
      {
        property: "og:description",
        content: "Contrôle cryptographique des documents KOUROUMA AUTO PART par DJIBEXA ERP.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: VerifierDocument,
});

function VerifierDocument() {
  const { token } = FileRoute.useParams();
  const { t } = useLocale();
  useEffect(() => {
    document.title = t("verification.documentTitle");
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = t("verification.metaDescription");
    const openGraphTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    if (openGraphTitle) openGraphTitle.content = t("verification.documentTitle");
    const openGraphDescription = document.querySelector<HTMLMetaElement>(
      'meta[property="og:description"]',
    );
    if (openGraphDescription) openGraphDescription.content = t("verification.metaDescription");
  }, [t]);

  const { data, isLoading } = useQuery({
    queryKey: ["verify-document", token],
    queryFn: async () => {
      try {
        const invoice = await api.get<{
          valid: boolean;
          signature_valid: boolean;
          signature_status: string;
          status: string;
          invoice_number: string;
          issue_date: string;
          total_amount: number;
          company_name: string;
          kind: string;
          items_count: number;
        }>(`invoices/verify/${token}/`);
        return {
          ...invoice,
          kind: "facture",
          number: invoice.invoice_number,
          created_at: invoice.issue_date,
          total: invoice.total_amount,
          party: invoice.company_name,
          signature_valid: invoice.signature_valid,
          signature_status: invoice.signature_status,
          status:
            invoice.signature_status === "cancelled"
              ? "annulee"
              : invoice.signature_valid
                ? "validated"
                : invoice.signature_status,
        };
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
        try {
          return await api
            .get<{
              valid: boolean;
              status: string;
              kind: string;
              number: string;
              created_at: string;
              customer?: string;
              items_count: number;
            }>(`documents/delivery-notes/verify/${token}/`)
            .then((delivery) => ({
              ...delivery,
              party: "",
              total: 0,
            }));
        } catch (deliveryError) {
          if (deliveryError instanceof ApiError && deliveryError.status === 404) return null;
          throw deliveryError;
        }
      }
    },
  });
  const cancelled = data?.status === "annulee" || data?.status === "cancelled";
  const signatureUnverified =
    data?.kind === "facture" && !cancelled && data.signature_valid !== true;
  const kindKey = signatureUnverified
    ? "verification.unsigned"
    : data?.kind === "facture"
      ? "verification.invoice"
      : data?.kind === "commande"
        ? "verification.order"
        : data?.kind === "livraison" || data?.kind === "delivery"
          ? "verification.delivery"
          : "verification.document";

  return (
    <div className="bg-background relative flex min-h-screen items-center justify-center px-4 py-10">
      <div className="absolute top-4 end-4">
        <LanguageSwitcher />
      </div>
      <div className="w-full max-w-md space-y-5">
        <div className="flex items-center justify-center gap-3">
          <img src={brandLogo} alt={t("landing.logoAlt")} className="size-14 object-contain" />
          <div>
            <p className="font-display text-lg font-bold uppercase">DJIBEXA</p>
            <p className="text-muted-foreground text-xs">{t("verification.heading")}</p>
          </div>
        </div>

        <div className="panel p-6">
          {isLoading ? (
            <p className="text-muted-foreground text-center text-sm">{t("verification.loading")}</p>
          ) : data ? (
            <div className="space-y-4">
              <div
                className={`flex items-center justify-center gap-2 ${cancelled || signatureUnverified ? "text-destructive" : "text-primary"}`}
              >
                {cancelled || signatureUnverified ? (
                  <ShieldAlert className="size-6" />
                ) : (
                  <BadgeCheck className="size-6" />
                )}
                <span className="font-semibold uppercase">{t(kindKey)}</span>
              </div>
              {cancelled && (
                <p className="border-destructive text-destructive mx-auto w-fit rounded border-2 px-3 py-1 text-sm font-bold tracking-widest uppercase">
                  {t("verification.cancelled")}
                </p>
              )}
              <dl className="divide-border divide-y text-sm">
                <div className="flex justify-between py-2">
                  <dt className="text-muted-foreground">{t("verification.number")}</dt>
                  <dd className="font-mono font-medium">{data.number}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-muted-foreground">{t("verification.date")}</dt>
                  <dd>{dateTime(data.created_at)}</dd>
                </div>
                {Number(data.total) > 0 && (
                  <div className="flex justify-between py-2">
                    <dt className="text-muted-foreground">{t("verification.amount")}</dt>
                    <dd className="font-semibold">{money(data.total)}</dd>
                  </div>
                )}
                <div className="flex justify-between py-2">
                  <dt className="text-muted-foreground">{t("verification.status")}</dt>
                  <dd>
                    {cancelled
                      ? t("verification.cancelled")
                      : signatureUnverified
                        ? t("verification.unsignedStatus")
                        : t("verification.valid")}
                  </dd>
                </div>
                {data.party && (
                  <div className="flex justify-between py-2">
                    <dt className="text-muted-foreground">
                      {data.kind === "commande"
                        ? t("verification.supplier")
                        : t("verification.customer")}
                    </dt>
                    <dd>{data.party}</dd>
                  </div>
                )}
                <div className="flex justify-between py-2">
                  <dt className="text-muted-foreground">{t("verification.lines")}</dt>
                  <dd>{data.items_count}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="space-y-3 text-center">
              <ShieldAlert className="text-destructive mx-auto size-8" />
              <p className="font-semibold uppercase">{t("verification.notFound")}</p>
              <p className="text-muted-foreground text-sm">
                {t("verification.notFoundDescription")}
              </p>
            </div>
          )}
        </div>

        <div className="panel p-4">
          <PartnerStrip surface="invoice" className="justify-center" />
        </div>

        <Button asChild variant="outline" className="w-full">
          <Link to="/">{t("verification.backHome")}</Link>
        </Button>
      </div>
    </div>
  );
}
