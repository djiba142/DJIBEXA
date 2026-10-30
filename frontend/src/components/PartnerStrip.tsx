import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";

type Surface = "invoice" | "orders";

const FALLBACK = {
  id: "bsg",
  name: "BSG Auto Parts",
  tagline: "Based on Safety Guarantee",
  logo_url: "",
};

/** Bandeau « partenaire officiel » affiché sur les documents. */
export function PartnerStrip({
  surface,
  className = "",
}: {
  surface: Surface;
  className?: string;
}) {
  const { t } = useLocale();
  const { can } = useAuth();
  const { data, isError } = useQuery({
    queryKey: ["partners", surface],
    enabled: can("partners.view"),
    queryFn: () =>
      api.list<{
        id: number;
        name: string;
        tagline: string;
        logo_url: string;
      }>("core/partners/", { surface }),
  });
  if (isError) {
    return <p className="text-destructive text-xs">{t("partnerStrip.loadError")}</p>;
  }
  const partners = data?.length ? data : [FALLBACK];

  return (
    <div className={`flex flex-wrap items-center justify-end gap-4 ${className}`}>
      {partners.map((p) => (
        <div key={p.id} className="flex items-center gap-2 text-right">
          <div>
            <p className="text-muted-foreground text-[10px] tracking-widest uppercase">
              {t("partnerStrip.official")}
            </p>
            <p className="text-xs font-semibold uppercase">{p.name}</p>
            {"tagline" in p && p.tagline && (
              <p className="text-muted-foreground text-[10px]">
                {p.tagline === "Based on Safety Guarantee" ? t("partnerStrip.tagline") : p.tagline}
              </p>
            )}
          </div>
          {p.logo_url && (
            <img
              src={p.logo_url}
              alt={`${p.name}, ${t("partnerStrip.official")}`}
              className="size-14 rounded-md object-contain"
              onError={(event) => {
                event.currentTarget.hidden = true;
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
