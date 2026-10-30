import { Route as FileRoute } from "@/routes/_authenticated/inventaire/$inventoryId";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, CheckCircle2, Printer } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

const PERIOD_KEYS: Record<string, string> = {
  journalier: "inventory.period.daily",
  mensuel: "inventory.period.monthly",
  trimestriel: "inventory.period.quarterly",
  annuel: "inventory.period.yearly",
};

function periodLabel(period: string, t: (key: string) => string) {
  const key = PERIOD_KEYS[period];
  return key ? t(key) : period;
}

export const PageRoute = createFileRoute("/_authenticated/inventaire/$inventoryId")({
  head: () => ({
    meta: [
      { title: "Feuille d'inventaire — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Feuille de comptage : saisie des quantités physiques, écarts par référence et validation de l'inventaire.",
      },
      { property: "og:title", content: "Feuille d'inventaire — DJIBEXA" },
      {
        property: "og:description",
        content: "Saisie du comptage physique et régularisation des écarts de stock.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="inventory.view">
      <FeuilleInventaire />
    </RequirePermission>
  ),
});

function FeuilleInventaire() {
  const { inventoryId } = FileRoute.useParams();
  const { t } = useLocale();
  const qc = useQueryClient();
  const { can, hasRole } = useAuth();
  const manage = can("inventory.manage");
  const [search, setSearch] = useState("");
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [notes, setNotes] = useState("");

  const { data: inventory } = useQuery({
    queryKey: ["inventory", inventoryId],
    queryFn: () =>
      api.get<{
        id: number;
        number: string;
        period_type: string;
        status: "draft" | "submitted" | "validated";
        notes: string;
        created_at: string;
        submitted_at: string | null;
        validated_at: string | null;
        location_name: string;
        items: {
          id: number;
          theoretical_quantity: number;
          counted_quantity: number;
          product_name: string;
          product_sku: string;
        }[];
      }>(`inventory/counts/${inventoryId}/`),
  });
  const lines = useMemo(
    () =>
      inventory?.items.map((line) => ({
        ...line,
        id: String(line.id),
        products: { name: line.product_name, reference: line.product_sku },
      })) ?? [],
    [inventory?.items],
  );

  useEffect(() => {
    if (!lines) return;
    setCounts(Object.fromEntries(lines.map((l) => [l.id, l.counted_quantity])));
  }, [lines]);

  useEffect(() => {
    if (inventory) setNotes(inventory.notes ?? "");
  }, [inventory]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return lines ?? [];
    return (lines ?? []).filter(
      (l) =>
        (l.products?.name ?? "").toLowerCase().includes(q) ||
        (l.products?.reference ?? "").toLowerCase().includes(q),
    );
  }, [lines, search]);

  const gaps = (lines ?? []).filter(
    (l) => (counts[l.id] ?? l.counted_quantity) !== l.theoretical_quantity,
  ).length;

  const locked = inventory?.status !== "draft" || !manage;

  const saveCounts = useMutation({
    mutationFn: async () => {
      await api.patch(`inventory/counts/${inventoryId}/`, {
        notes,
        items: (lines ?? []).map((line) => ({
          id: Number(line.id),
          counted_quantity: counts[line.id] ?? line.counted_quantity,
        })),
      });
    },
    onSuccess: () => {
      toast.success(t("inventory.countSaved"));
      void qc.invalidateQueries({ queryKey: ["inventory", inventoryId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const validate = useMutation({
    mutationFn: async () => {
      await api.post(`inventory/counts/${inventoryId}/validate/`);
    },
    onSuccess: () => {
      toast.success(t("inventory.validatedToast"), {
        description: t("inventory.validatedDescription"),
      });
      void qc.invalidateQueries({ queryKey: ["inventory", inventoryId] });
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["stock"] });
      void qc.invalidateQueries({ queryKey: ["movements"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = useMutation({
    mutationFn: async () => {
      await saveCounts.mutateAsync();
      await api.post(`inventory/counts/${inventoryId}/submit/`);
    },
    onSuccess: () => {
      toast.success(t("inventory.submittedToast"));
      void qc.invalidateQueries({ queryKey: ["inventory", inventoryId] });
      void qc.invalidateQueries({ queryKey: ["inventories"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div>
          <Button asChild variant="ghost" size="sm" className="mb-1 -ml-2">
            <Link to="/inventaire">
              <ArrowLeft className="size-4" /> {t("inventory.back")}
            </Link>
          </Button>
          <h1 className="font-mono text-2xl font-bold">{inventory?.number ?? "…"}</h1>
          <p className="text-muted-foreground text-sm">
            {inventory ? periodLabel(inventory.period_type, t) : ""} ·{" "}
            {inventory?.location_name ?? t("inventory.unknownLocation")} ·{" "}
            {inventory ? dateTime(inventory.created_at) : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={inventory?.status === "validated" ? "default" : "secondary"}>
            {inventory?.status === "validated"
              ? t("inventory.validated")
              : inventory?.status === "submitted"
                ? t("inventory.submitted")
                : t("inventory.inProgress")}
          </Badge>
          <Badge variant="outline">
            {gaps} {t("inventory.gap")}
          </Badge>
          <Button variant="outline" onClick={() => window.print()}>
            <Printer className="size-4" /> {t("inventory.print")}
          </Button>
          {!locked && (
            <>
              <Button
                variant="outline"
                onClick={() => saveCounts.mutate()}
                disabled={saveCounts.isPending}
              >
                {t("inventory.save")}
              </Button>
              <Button onClick={() => submit.mutate()} disabled={submit.isPending}>
                <CheckCircle2 className="size-4" /> {t("inventory.submit")}
              </Button>
            </>
          )}
          {hasRole("admin") && inventory?.status === "submitted" && (
            <Button onClick={() => validate.mutate()} disabled={validate.isPending}>
              <CheckCircle2 className="size-4" /> {t("inventory.validate")}
            </Button>
          )}
        </div>
      </div>

      <Input
        placeholder={t("inventory.search")}
        className="w-full max-w-sm print:hidden"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      <div className="max-w-2xl print:hidden">
        <Textarea
          aria-label={t("inventory.notes")}
          placeholder={t("inventory.notes")}
          disabled={locked}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventory.product")}</TableHead>
              <TableHead className="text-right">{t("inventory.theoretical")}</TableHead>
              <TableHead className="w-32 text-right">{t("inventory.counted")}</TableHead>
              <TableHead className="text-right">{t("inventory.difference")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((l) => {
              const counted = counts[l.id] ?? l.counted_quantity;
              const gap = counted - l.theoretical_quantity;
              return (
                <TableRow key={l.id}>
                  <TableCell>
                    <p className="font-medium">{l.products?.name}</p>
                    <p className="text-muted-foreground font-mono text-xs">
                      {l.products?.reference}
                    </p>
                  </TableCell>
                  <TableCell className="text-right">{l.theoretical_quantity}</TableCell>
                  <TableCell className="text-right">
                    <Input
                      type="number"
                      min={0}
                      className="ml-auto h-8 w-24 text-right"
                      disabled={locked}
                      value={counted}
                      onChange={(e) =>
                        setCounts((prev) => ({ ...prev, [l.id]: Number(e.target.value) || 0 }))
                      }
                    />
                  </TableCell>
                  <TableCell
                    className={`text-right font-medium ${gap === 0 ? "text-muted-foreground" : gap > 0 ? "text-primary" : "text-destructive"}`}
                  >
                    {gap > 0 ? `+${gap}` : gap}
                  </TableCell>
                </TableRow>
              );
            })}
            {!filtered.length && (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground py-10 text-center">
                  {t("inventory.noLines")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
