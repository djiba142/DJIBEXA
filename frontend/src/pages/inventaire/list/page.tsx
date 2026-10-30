import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ClipboardList, Plus } from "lucide-react";
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
import { docNumber } from "@/lib/qr";

export const PageRoute = createFileRoute("/_authenticated/inventaire/")({
  head: () => ({
    meta: [
      { title: "Inventaires — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Inventaires journaliers, mensuels, trimestriels et annuels : comptage physique, écarts et régularisation du stock.",
      },
      { property: "og:title", content: "Inventaires — DJIBEXA" },
      {
        property: "og:description",
        content: "Comptage du stock par période et régularisation automatique des écarts.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="inventory.view">
      <Inventaires />
    </RequirePermission>
  ),
});

export const PERIOD_KEYS: Record<string, string> = {
  journalier: "inventory.period.daily",
  mensuel: "inventory.period.monthly",
  trimestriel: "inventory.period.quarterly",
  annuel: "inventory.period.yearly",
};

function periodLabel(period: string, t: (key: string) => string) {
  const key = PERIOD_KEYS[period];
  return key ? t(key) : period;
}

function Inventaires() {
  const { t } = useLocale();
  const qc = useQueryClient();
  const { can } = useAuth();
  const manage = can("inventory.manage");
  const [open, setOpen] = useState(false);
  const [period, setPeriod] = useState("journalier");
  const [warehouse, setWarehouse] = useState("");
  const [notes, setNotes] = useState("");

  const { data: inventories } = useQuery({
    queryKey: ["inventories"],
    queryFn: () =>
      api.list<{
        id: number;
        number: string;
        period_type: string;
        status: "draft" | "submitted" | "validated";
        created_at: string;
        validated_at: string | null;
        location_name: string;
      }>("inventory/counts/"),
  });

  const { data: warehouses } = useQuery({
    queryKey: ["warehouses-min"],
    queryFn: () =>
      api.list<{ id: number; name: string; is_active: boolean }>("inventory/locations/"),
  });

  const create = useMutation({
    mutationFn: async () => {
      const locationId = warehouse || String(warehouses?.[0]?.id ?? "");
      if (!locationId) throw new Error(t("inventory.createError"));
      const inventory = await api.post<{ id: number }>("inventory/counts/", {
        number: docNumber("INV"),
        period_type: period,
        location: Number(locationId),
        notes,
      });
      return String(inventory.id);
    },
    onSuccess: () => {
      toast.success(t("inventory.createdToast"), {
        description: t("inventory.createdDescription"),
      });
      setOpen(false);
      setNotes("");
      void qc.invalidateQueries({ queryKey: ["inventories"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("inventory.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("inventory.description")}</p>
        </div>
        {manage && (
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" /> {t("inventory.new")}
          </Button>
        )}
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventory.number")}</TableHead>
              <TableHead>{t("inventory.period")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("inventory.location")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("inventory.createdAt")}</TableHead>
              <TableHead>{t("inventory.status")}</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(inventories ?? []).map((inv) => (
              <TableRow key={inv.id}>
                <TableCell className="font-mono text-xs">{inv.number}</TableCell>
                <TableCell>{periodLabel(inv.period_type, t)}</TableCell>
                <TableCell className="hidden sm:table-cell">{inv.location_name}</TableCell>
                <TableCell className="hidden sm:table-cell">{dateTime(inv.created_at)}</TableCell>
                <TableCell>
                  <Badge variant={inv.status === "validated" ? "default" : "secondary"}>
                    {inv.status === "validated"
                      ? t("inventory.validated")
                      : inv.status === "submitted"
                        ? t("inventory.submitted")
                        : t("inventory.inProgress")}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild size="sm" variant="outline">
                    <Link to="/inventaire/$inventoryId" params={{ inventoryId: String(inv.id) }}>
                      <ClipboardList className="size-4" /> {t("inventory.open")}
                    </Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!inventories?.length && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground py-10 text-center">
                  {t("inventory.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("inventory.new")}</DialogTitle>
            <DialogDescription>{t("inventory.newDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t("inventory.period")}</Label>
              <Select value={period} onValueChange={setPeriod}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.keys(PERIOD_KEYS).map((k) => (
                    <SelectItem key={k} value={k}>
                      {periodLabel(k, t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t("inventory.location")}</Label>
              <Select value={warehouse} onValueChange={setWarehouse}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(warehouses ?? []).map((w) => (
                    <SelectItem key={w.id} value={String(w.id)}>
                      {w.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="inv-notes">{t("inventory.notes")}</Label>
              <Textarea id="inv-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("inventory.cancel")}
            </Button>
            <Button
              onClick={() => create.mutate()}
              disabled={create.isPending || !warehouses?.length}
            >
              {t("inventory.createSheet")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
