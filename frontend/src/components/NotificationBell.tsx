import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Bell } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import { brandMark } from "@/lib/brand-assets";
import { useLocale } from "@/lib/locale";

export type NotificationRow = {
  id: number;
  type: string;
  title: string;
  body: string | null;
  data: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
};

export function useNotifications(limit = 20) {
  const { session } = useAuth();
  const userId = session?.user.id;

  const query = useQuery({
    queryKey: ["notifications", userId, limit],
    enabled: !!userId,
    refetchInterval: 30_000,
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          event_type: string;
          message: string;
          sale: number | null;
          is_read: boolean;
          read_at: string | null;
          created_at: string;
        }>("notifications/")
      )
        .map((notification): NotificationRow => ({
          id: notification.id,
          type: notification.event_type,
          title: notification.event_type.replaceAll("_", " "),
          body: notification.message,
          data: notification.sale === null ? null : { sale_id: String(notification.sale) },
          read_at: notification.is_read ? (notification.read_at ?? notification.created_at) : null,
          created_at: notification.created_at,
        }))
        .slice(0, limit),
  });

  return query;
}

export async function markAllRead() {
  const notifications = await api.list<{
    id: number;
    is_read: boolean;
  }>("notifications/");
  await Promise.all(
    notifications
      .filter((notification) => !notification.is_read)
      .map((notification) => api.post(`notifications/${notification.id}/read/`)),
  );
}

export function NotificationBell() {
  const qc = useQueryClient();
  const { t } = useLocale();
  const { data } = useNotifications(10);
  const unread = (data ?? []).filter((n) => !n.read_at).length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative size-10"
          aria-label={t("nav.notifications")}
        >
          <Bell className="size-5" />
          {unread > 0 && (
            <span className="bg-destructive text-destructive-foreground absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full text-[10px] font-bold">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(20rem,calc(100vw-1.5rem))] p-0">
        <div className="flex items-center justify-between border-b p-3">
          <p className="text-sm font-semibold uppercase">{t("nav.notifications")}</p>
          {unread > 0 && (
            <button
              className="text-primary text-xs"
              onClick={() =>
                void markAllRead()
                  .then(() => qc.invalidateQueries({ queryKey: ["notifications"] }))
                  .catch((error: unknown) =>
                    toast.error(t("common.updateError"), {
                      description:
                        error instanceof Error ? error.message : t("common.unknownError"),
                    }),
                  )
              }
            >
              {t("notifications.markAllRead")}
            </button>
          )}
        </div>
        <div className="max-h-80 overflow-y-auto">
          {(data ?? []).map((n) => (
            <div
              key={n.id}
              className={`flex gap-2 border-b p-3 text-sm last:border-b-0 ${n.read_at ? "" : "bg-accent/40"}`}
            >
              <img src={brandMark} alt="" className="mt-0.5 size-4 shrink-0" />
              <div className="min-w-0">
                <p className="font-medium">{notificationTitle(n.type, n.title, t)}</p>
                {n.body && <p className="text-muted-foreground text-xs">{n.body}</p>}
                <p className="text-muted-foreground mt-1 text-[11px]">{dateTime(n.created_at)}</p>
              </div>
            </div>
          ))}
          {!data?.length && (
            <p className="text-muted-foreground p-6 text-center text-sm">
              {t("notifications.none")}
            </p>
          )}
        </div>
        <div className="border-t p-2">
          <Button asChild variant="ghost" size="sm" className="w-full">
            <Link to="/notifications">{t("notifications.viewAll")}</Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
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
