import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Pencil, Plus, Trash2 } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/partenaires")({
  head: () => ({
    meta: [
      { title: "Partenaires officiels — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Gérez les partenaires officiels du magasin : logo, coordonnées WhatsApp et affichage sur les factures et bons de commande.",
      },
      { property: "og:title", content: "Partenaires officiels — DJIBEXA" },
      {
        property: "og:description",
        content: "Logos et coordonnées des partenaires affichés sur les documents commerciaux.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="partners.view">
      <Partenaires />
    </RequirePermission>
  ),
});

type FormState = {
  id?: number;
  name: string;
  tagline: string;
  logo_url: string;
  phone: string;
  whatsapp: string;
  email: string;
  website: string;
  notes: string;
  show_on_invoice: boolean;
  show_on_orders: boolean;
  active: boolean;
};

const EMPTY: FormState = {
  name: "",
  tagline: "",
  logo_url: "",
  phone: "",
  whatsapp: "",
  email: "",
  website: "",
  notes: "",
  show_on_invoice: true,
  show_on_orders: true,
  active: true,
};

function Partenaires() {
  const { t } = useLocale();
  const qc = useQueryClient();
  const { can } = useAuth();
  const manage = can("partners.manage");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY);

  const { data: partners } = useQuery({
    queryKey: ["partners-admin"],
    queryFn: () => api.list<FormState & { id: number }>("core/partners/manage/"),
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!form.name.trim()) throw new Error(t("partners.nameRequired"));
      const payload = {
        name: form.name.trim(),
        tagline: form.tagline,
        logo_url: form.logo_url,
        phone: form.phone,
        whatsapp: form.whatsapp,
        email: form.email,
        website: form.website,
        notes: form.notes,
        show_on_invoice: form.show_on_invoice,
        show_on_orders: form.show_on_orders,
        active: form.active,
      };
      if (form.id) {
        await api.patch(`core/partners/manage/${form.id}/`, payload);
      } else {
        await api.post("core/partners/manage/", payload);
      }
    },
    onSuccess: () => {
      toast.success(t("partners.saved"));
      setOpen(false);
      setForm(EMPTY);
      void qc.invalidateQueries({ queryKey: ["partners-admin"] });
      void qc.invalidateQueries({ queryKey: ["partners"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: async (id: number) => api.patch(`core/partners/manage/${id}/`, { active: false }),
    onSuccess: () => {
      toast.success(t("partners.deactivated"));
      void qc.invalidateQueries({ queryKey: ["partners-admin"] });
      void qc.invalidateQueries({ queryKey: ["partners"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("partners.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("partners.description")}</p>
        </div>
        {manage && (
          <Button
            onClick={() => {
              setForm(EMPTY);
              setOpen(true);
            }}
          >
            <Plus className="size-4" /> {t("partners.new")}
          </Button>
        )}
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("partners.partner")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("partners.contact")}</TableHead>
              <TableHead>{t("partners.display")}</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(partners ?? []).map((p) => (
              <TableRow key={p.id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    {p.logo_url && (
                      <img
                        src={p.logo_url}
                        alt={p.name}
                        className="size-10 rounded-md object-contain"
                      />
                    )}
                    <div>
                      <p className="font-medium">{p.name}</p>
                      <p className="text-muted-foreground text-xs">{p.tagline ?? "—"}</p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="hidden text-xs sm:table-cell">
                  <p>{p.whatsapp || p.phone || "—"}</p>
                  <p className="text-muted-foreground">{p.website || p.email || ""}</p>
                </TableCell>
                <TableCell className="space-x-1">
                  {p.show_on_invoice && <Badge variant="secondary">{t("partners.invoices")}</Badge>}
                  {p.show_on_orders && <Badge variant="secondary">{t("partners.orders")}</Badge>}
                  {!p.active && <Badge variant="outline">{t("partners.inactive")}</Badge>}
                </TableCell>
                <TableCell className="text-right">
                  {manage && (
                    <div className="flex justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`${t("partners.edit")} ${p.name}`}
                        onClick={() => {
                          setForm({
                            id: p.id,
                            name: p.name,
                            tagline: p.tagline ?? "",
                            logo_url: p.logo_url ?? "",
                            phone: p.phone ?? "",
                            whatsapp: p.whatsapp ?? "",
                            email: p.email ?? "",
                            website: p.website ?? "",
                            notes: p.notes ?? "",
                            show_on_invoice: p.show_on_invoice,
                            show_on_orders: p.show_on_orders,
                            active: p.active,
                          });
                          setOpen(true);
                        }}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`${t("partners.remove")} ${p.name}`}
                        onClick={() => remove.mutate(p.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!partners?.length && (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground py-10 text-center">
                  {t("partners.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{form.id ? t("partners.edit") : t("partners.new")}</DialogTitle>
            <DialogDescription>{t("partners.dialogDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="p-name">{t("partners.name")}</Label>
              <Input
                id="p-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="p-tag">{t("partners.tagline")}</Label>
              <Input
                id="p-tag"
                value={form.tagline}
                onChange={(e) => setForm({ ...form, tagline: e.target.value })}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="p-logo">{t("partners.logoUrl")}</Label>
              <Input
                id="p-logo"
                placeholder="https://…"
                value={form.logo_url}
                onChange={(e) => setForm({ ...form, logo_url: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="p-phone">{t("customers.phone")}</Label>
              <Input
                id="p-phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="p-wa">{t("partners.whatsapp")}</Label>
              <Input
                id="p-wa"
                placeholder="224 6xx xx xx xx"
                value={form.whatsapp}
                onChange={(e) => setForm({ ...form, whatsapp: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="p-mail">{t("partners.email")}</Label>
              <Input
                id="p-mail"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="p-web">{t("partners.website")}</Label>
              <Input
                id="p-web"
                value={form.website}
                onChange={(e) => setForm({ ...form, website: e.target.value })}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="p-notes">{t("partners.notes")}</Label>
              <Textarea
                id="p-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <Label htmlFor="p-inv">{t("partners.onInvoices")}</Label>
              <Switch
                id="p-inv"
                checked={form.show_on_invoice}
                onCheckedChange={(v) => setForm({ ...form, show_on_invoice: v })}
              />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <Label htmlFor="p-ord">{t("partners.onOrders")}</Label>
              <Switch
                id="p-ord"
                checked={form.show_on_orders}
                onCheckedChange={(v) => setForm({ ...form, show_on_orders: v })}
              />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3 sm:col-span-2">
              <Label htmlFor="p-active">{t("partners.active")}</Label>
              <Switch
                id="p-active"
                checked={form.active}
                onCheckedChange={(v) => setForm({ ...form, active: v })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
