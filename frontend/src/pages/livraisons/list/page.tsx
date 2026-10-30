import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { FileText, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
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
import { dateTime } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/livraisons/")({
  head: () => ({
    meta: [
      { title: "Bons de livraison — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Créez et imprimez les bons de livraison avec QR code de vérification, à partir des ventes du magasin.",
      },
      { property: "og:title", content: "Bons de livraison — DJIBEXA" },
      {
        property: "og:description",
        content: "Documents de livraison avec QR code d'authenticité.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="deliveries.view">
      <Livraisons />
    </RequirePermission>
  ),
});

const DELIVERY_STATUS_KEYS: Record<string, string> = {
  prepared: "delivery.prepared",
  delivered: "delivery.delivered",
  cancelled: "delivery.cancelled",
};

function deliveryStatusLabel(status: string, t: (key: string) => string) {
  const key = DELIVERY_STATUS_KEYS[status];
  return key ? t(key) : status;
}

function Livraisons() {
  const { t } = useLocale();
  const qc = useQueryClient();
  const { can } = useAuth();
  const manage = can("deliveries.manage");
  const [open, setOpen] = useState(false);
  const [saleId, setSaleId] = useState("");
  const [notes, setNotes] = useState("");

  const { data: notes_ } = useQuery({
    queryKey: ["delivery-notes"],
    queryFn: () =>
      api.list<{
        id: number;
        reference: string;
        status: string;
        created_at: string;
        customer_name: string;
        sale_reference: string;
      }>("documents/delivery-notes/"),
  });

  const { data: sales } = useQuery({
    queryKey: ["sales-for-delivery"],
    queryFn: () =>
      api
        .list<{
          id: number;
          invoice_number: string | null;
          customer: number | null;
          customer_name: string;
        }>("sales/")
        .then((rows) =>
          rows.map((sale) => ({
            id: String(sale.id),
            number: sale.invoice_number ?? `VTE-${sale.id}`,
            customer_id: sale.customer,
            customers: { name: sale.customer_name },
          })),
        ),
  });

  const create = useMutation({
    mutationFn: async () => {
      const sale = (sales ?? []).find((s) => s.id === saleId);
      if (!sale) throw new Error(t("delivery.chooseSaleError"));
      await api.post("documents/delivery-notes/", { sale: Number(sale.id), notes });
    },
    onSuccess: () => {
      toast.success(t("delivery.created"));
      setOpen(false);
      setSaleId("");
      setNotes("");
      void qc.invalidateQueries({ queryKey: ["delivery-notes"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("delivery.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("delivery.description")}</p>
        </div>
        {manage && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" /> {t("delivery.new")}
          </Button>
        )}
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("delivery.number")}</TableHead>
              <TableHead>{t("delivery.customer")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("delivery.sale")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("delivery.date")}</TableHead>
              <TableHead>{t("delivery.status")}</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(notes_ ?? []).map((d) => (
              <TableRow key={d.id}>
                <TableCell className="font-mono text-xs">{d.reference}</TableCell>
                <TableCell>{d.customer_name || "Client comptoir"}</TableCell>
                <TableCell className="hidden font-mono text-xs sm:table-cell">
                  {d.sale_reference}
                </TableCell>
                <TableCell className="hidden sm:table-cell">{dateTime(d.created_at)}</TableCell>
                <TableCell>
                  <Badge variant={d.status === "delivered" ? "default" : "secondary"}>
                    {deliveryStatusLabel(d.status, t)}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild size="sm" variant="outline">
                    <Link to="/livraisons/$deliveryId" params={{ deliveryId: String(d.id) }}>
                      <FileText className="size-4" /> {t("delivery.open")}
                    </Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!notes_?.length && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground py-10 text-center">
                  {t("delivery.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("delivery.newTitle")}</DialogTitle>
            <DialogDescription>{t("delivery.newDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t("delivery.sale")}</Label>
              <Select value={saleId} onValueChange={setSaleId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("delivery.chooseSale")} />
                </SelectTrigger>
                <SelectContent>
                  {(sales ?? []).map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.number} · {s.customers?.name ?? t("sales.customerCounter")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="bl-notes">{t("delivery.notes")}</Label>
              <Textarea id="bl-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("delivery.cancel")}
            </Button>
            <Button onClick={() => create.mutate()} disabled={create.isPending}>
              {t("delivery.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
