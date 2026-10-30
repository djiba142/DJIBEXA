import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";

import { NotificationBell, markAllRead, useNotifications } from "@/components/NotificationBell";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { brandMark } from "@/lib/brand-assets";
import { useLocale } from "@/lib/locale";
import { toast } from "sonner";

export const PageRoute = createFileRoute("/_authenticated/notifications")({
  head: () => ({
    meta: [
      { title: "Notifications — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Historique des notifications de ventes et de demandes d'approvisionnement de la boutique.",
      },
      { property: "og:title", content: "Notifications — DJIBEXA" },
      { property: "og:description", content: "Suivi en temps réel de l'activité de la boutique." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: NotificationsPage,
});

function NotificationsPage() {
  const qc = useQueryClient();
  const { t } = useLocale();
  const { data } = useNotifications(200);
  const unread = (data ?? []).filter((n) => !n.read_at).length;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("notifications.history")}</h1>
          <p className="text-muted-foreground text-sm">
            {unread} {t(unread === 1 ? "notifications.unread" : "notifications.unreadPlural")} ·{" "}
            {t("notifications.history")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <NotificationBell />
          <Button
            variant="outline"
            disabled={!unread}
            onClick={() =>
              void markAllRead()
                .then(() => qc.invalidateQueries({ queryKey: ["notifications"] }))
                .catch((error: unknown) =>
                  toast.error(t("notifications.markError"), {
                    description: error instanceof Error ? error.message : t("common.unknownError"),
                  }),
                )
            }
          >
            {t("notifications.markAllRead")}
          </Button>
        </div>
      </div>

      <div className="panel divide-y">
        {(data ?? []).map((n) => {
          const saleId = (n.data?.["sale_id"] as string | undefined) ?? null;
          return (
            <div key={n.id} className={`p-4 ${n.read_at ? "" : "bg-accent/30"}`}>
              <div className="flex items-start gap-3">
                <img src={brandMark} alt="" className="mt-1 size-5 shrink-0" />
                <div className="flex min-w-0 flex-1 flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{notificationTitle(n.type, n.title, t)}</p>
                    {n.body && <p className="text-muted-foreground text-sm">{n.body}</p>}
                    <p className="text-muted-foreground mt-1 text-xs">{dateTime(n.created_at)}</p>
                  </div>
                  {saleId && (
                    <Button asChild size="sm" variant="outline">
                      <Link to="/ventes/$saleId" params={{ saleId }}>
                        {t("notifications.viewSale")}
                      </Link>
                    </Button>
                  )}
                  {n.type === "credit_reminder" && (
                    <Button asChild size="sm" variant="outline">
                      <Link to="/credits">{t("notifications.viewCredits")}</Link>
                    </Button>
                  )}
                  {!n.read_at && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        void api
                          .post(`notifications/${n.id}/read/`)
                          .then(() => qc.invalidateQueries({ queryKey: ["notifications"] }))
                          .catch((error: unknown) =>
                            toast.error(t("notifications.markError"), {
                              description:
                                error instanceof Error ? error.message : t("common.unknownError"),
                            }),
                          )
                      }
                    >
                      {t("notifications.markRead")}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {!data?.length && (
          <p className="text-muted-foreground p-10 text-center text-sm">
            {t("notifications.none")}
          </p>
        )}
      </div>
    </div>
  );
}

function notificationTitle(type: string, fallback: string, t: (key: string) => string) {
  const keys: Record<string, string> = {
    sale_confirmed: "notifications.sale",
    payment_received: "notifications.payment",
    invoice_sent: "notifications.invoice",
    credit_reminder: "notifications.creditReminder",
    stock_replenishment_requested: "notifications.replenishmentRequest",
  };
  return keys[type] ? t(keys[type]) : fallback;
}
