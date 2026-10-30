import { useSettings } from "@/lib/settings";
import { useLocale } from "@/lib/locale";

/** En-tête entreprise des documents, alimenté par les Paramètres. */
export function CompanyHeader({ size = "xl" }: { size?: "lg" | "xl" }) {
  const s = useSettings();
  const { t } = useLocale();
  const contacts = [
    s.phone && `${t("company.phoneLabel")} ${s.phone}`,
    s.whatsapp && `${t("company.whatsappLabel")} ${s.whatsapp}`,
    s.email,
  ].filter(Boolean);
  const legal = [
    s.rccm && `${t("company.rccmLabel")} ${s.rccm}`,
    s.nif && `${t("company.nifLabel")} ${s.nif}`,
    s.vatRate ? `${t("company.vatLabel")} ${s.vatRate} %` : "",
  ].filter(Boolean);
  return (
    <div>
      <p className={`font-display font-bold uppercase ${size === "xl" ? "text-xl" : "text-lg"}`}>
        {s.companyName}
      </p>
      <p className="text-muted-foreground text-xs">
        {s.slogan} · {s.address}
      </p>
      {contacts.length > 0 && (
        <p className="text-muted-foreground text-xs">{contacts.join(" · ")}</p>
      )}
      {legal.length > 0 && <p className="text-muted-foreground text-xs">{legal.join(" · ")}</p>}
    </div>
  );
}

export function CompanyFooter() {
  const s = useSettings();
  const { t } = useLocale();
  return (
    <>
      {s.invoiceFooter} — {s.companyName}, {s.address}. {t("company.currencyLabel")} : {s.currency}.
    </>
  );
}
