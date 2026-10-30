import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatNumber, shortDate } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/clients")({
  head: () => ({
    meta: [
      { title: "Clients — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Fichier clients du magasin : nom, téléphone et adresse pour un suivi commercial simple.",
      },
      { property: "og:title", content: "Clients — DJIBEXA" },
      { property: "og:description", content: "Fichier clients et coordonnées." },
    ],
  }),
  component: Clients,
});

function Clients() {
  const { t } = useLocale();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({ name: "", phone: "", address: "" });

  const { data: customers } = useQuery({
    queryKey: ["customers"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          full_name: string;
          phone: string;
          address: string;
          created_at: string;
        }>("customers/")
      )
        .map((customer) => ({ ...customer, name: customer.full_name }))
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
  });

  const create = useMutation({
    mutationFn: async () => {
      await api.post("customers/", {
        full_name: form.name.trim(),
        phone: form.phone,
        address: form.address,
      });
    },
    onSuccess: () => {
      toast.success(t("customers.saved"));
      setForm({ name: "", phone: "", address: "" });
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (e: Error) => toast.error(t("customers.saveError"), { description: e.message }),
  });

  const filtered = (customers ?? []).filter((c) =>
    `${c.name} ${c.phone ?? ""}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("customers.title")}</h1>
          <p className="text-muted-foreground text-sm">
            {t("customers.count", { count: formatNumber(filtered.length) })}
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>{t("customers.add")}</Button>
      </div>

      <Input
        placeholder={t("customers.search")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-md"
      />

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("customers.name")}</TableHead>
              <TableHead>{t("customers.phone")}</TableHead>
              <TableHead className="hidden md:table-cell">{t("customers.address")}</TableHead>
              <TableHead className="text-right">{t("customers.created")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium">{c.name}</TableCell>
                <TableCell>{c.phone ?? "—"}</TableCell>
                <TableCell className="hidden md:table-cell">{c.address ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground text-right text-xs">
                  {shortDate(c.created_at)}
                </TableCell>
              </TableRow>
            ))}
            {!filtered.length && (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground py-10 text-center">
                  {t("customers.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("customers.new")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{t("customers.name")} *</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("customers.phone")}</Label>
              <Input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("customers.address")}</Label>
              <Input
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => create.mutate()} disabled={!form.name || create.isPending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
