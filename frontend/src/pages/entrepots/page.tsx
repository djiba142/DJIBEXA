import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { dateTime, formatNumber } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/entrepots")({
  head: () => ({
    meta: [
      { title: "Entrepôts & transferts — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Stock par emplacement, demandes d'approvisionnement de la boutique et transferts entre entrepôts.",
      },
      { property: "og:title", content: "Entrepôts & transferts — DJIBEXA" },
      {
        property: "og:description",
        content: "Gestion multi-emplacements et approvisionnement de la boutique.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequirePermission permission="warehouses.view">
      <Warehouses />
    </RequirePermission>
  ),
});

function Warehouses() {
  const { t } = useLocale();
  const { can, hasRole } = useAuth();
  const manage = can("transfers.manage");
  const qc = useQueryClient();

  const [newOpen, setNewOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("entrepot");
  const [address, setAddress] = useState("");
  const [authorizedUsers, setAuthorizedUsers] = useState<string[]>([]);

  const [requestId, setRequestId] = useState<string | null>(null);
  const [alloc, setAlloc] = useState<Record<string, string>>({});

  const { data: warehouses } = useQuery({
    queryKey: ["warehouses"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          name: string;
          location_type: string;
          address: string;
          is_active: boolean;
        }>("inventory/locations/")
      )
        .map((location) => ({
          id: String(location.id),
          name: location.name,
          kind: location.location_type === "shop" ? "boutique" : "entrepot",
          address: location.address,
          is_shop: location.location_type === "shop",
          active: location.is_active,
        }))
        .sort((a, b) => Number(b.is_shop) - Number(a.is_shop) || a.name.localeCompare(b.name)),
  });

  const { data: salesUsers } = useQuery({
    queryKey: ["shop-sales-users"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          first_name: string;
          last_name: string;
          username: string;
          role: string;
          roles?: string[];
          is_active: boolean;
        }>("users/")
      ).filter((user) => (user.roles ?? [user.role]).includes("sales") && user.is_active),
    enabled: hasRole("admin"),
  });

  const { data: stock } = useQuery({
    queryKey: ["product_stock"],
    queryFn: async () => {
      const [stockItems, products] = await Promise.all([
        api.list<{ product: number; location: number; quantity: number }>("inventory/stock/"),
        api.list<{ id: number; name: string; sku: string }>("products/"),
      ]);
      const productById = new Map(products.map((product) => [product.id, product]));
      return stockItems.map((item) => ({
        product_id: String(item.product),
        warehouse_id: String(item.location),
        quantity: item.quantity,
        products: productById.has(item.product)
          ? {
              name: productById.get(item.product)!.name,
              reference: productById.get(item.product)!.sku,
            }
          : null,
      }));
    },
  });

  const { data: requests } = useQuery({
    queryKey: ["supply_requests"],
    queryFn: async () => {
      return api.list<{
        id: number;
        reference: string;
        product: number;
        product_name: string;
        product_reference: string;
        shop: number;
        shop_name: string;
        requested_quantity: number;
        remaining_quantity: number;
        request_reason: string;
        refusal_reason: string;
        status: "requested" | "accepted" | "partially_received" | "rejected" | "completed";
        created_at: string;
      }>("inventory/replenishment-requests/");
    },
  });

  const { data: transfers } = useQuery({
    queryKey: ["transfers"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          reference: string;
          product_name: string;
          from_location: number;
          to_location: number;
          quantity: number;
          created_at: string;
          quantity_shipped: number;
          quantity_received: number | null;
          variance_reason: string;
          status: "requested" | "validated" | "shipped" | "received" | "cancelled";
        }>("inventory/transfers/")
      )
        .slice(0, 30)
        .map((transfer) => ({
          id: String(transfer.id),
          number: transfer.reference,
          created_at: transfer.created_at,
          quantity: transfer.quantity,
          quantity_shipped: transfer.quantity_shipped,
          quantity_received: transfer.quantity_received,
          variance_reason: transfer.variance_reason,
          status: transfer.status,
          to_warehouse_id: String(transfer.to_location),
          transfer_lines: [
            {
              quantity: transfer.quantity,
              from_warehouse_id: String(transfer.from_location),
              products: { name: transfer.product_name },
            },
          ],
        })),
  });

  const whName = useMemo(
    () => Object.fromEntries((warehouses ?? []).map((w) => [w.id, w.name])),
    [warehouses],
  );

  const activeRequest = (requests ?? []).find((r) => String(r.id) === requestId) ?? null;
  const sources = (stock ?? []).filter(
    (s) =>
      activeRequest &&
      s.product_id === String(activeRequest.product) &&
      s.quantity > 0 &&
      s.warehouse_id !== String(activeRequest.shop),
  );
  const allocTotal = Object.values(alloc).reduce((sum, v) => sum + (Number(v) || 0), 0);

  const createWarehouse = useMutation({
    mutationFn: async () => {
      await api.post("inventory/locations/", {
        name,
        code: `LOC-${Date.now()}`,
        location_type: kind === "boutique" ? "shop" : "warehouse",
        address,
        ...(kind === "boutique"
          ? { authorized_users: authorizedUsers.map((id) => Number(id)) }
          : {}),
      });
    },
    onSuccess: () => {
      toast.success(t("warehouse.created"));
      setNewOpen(false);
      setName("");
      setAddress("");
      setAuthorizedUsers([]);
      void qc.invalidateQueries({ queryKey: ["warehouses"] });
    },
    onError: (e: Error) => toast.error(t("warehouse.createError"), { description: e.message }),
  });

  const doTransfer = useMutation({
    mutationFn: async () => {
      if (!activeRequest) throw new Error(t("warehouse.notFound"));
      const lines = Object.entries(alloc)
        .map(([location, q]) => ({ location: Number(location), quantity: Number(q) || 0 }))
        .filter((line) => line.quantity > 0);
      if (!lines.length) throw new Error(t("warehouse.noQuantity"));
      return api.post(`inventory/replenishment-requests/${activeRequest.id}/accept/`, {
        allocations: lines,
      });
    },
    onSuccess: () => {
      toast.success(
        hasRole("stock") && !hasRole("admin")
          ? t("warehouse.transferRequested")
          : t("warehouse.accepted"),
      );
      setRequestId(null);
      setAlloc({});
      void qc.invalidateQueries({ queryKey: ["product_stock"] });
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["supply_requests"] });
      void qc.invalidateQueries({ queryKey: ["transfers"] });
    },
    onError: (e: Error) => toast.error(t("warehouse.transferError"), { description: e.message }),
  });

  const rejectRequest = useMutation({
    mutationFn: async ({ requestId, reason }: { requestId: number; reason: string }) =>
      api.post(`inventory/replenishment-requests/${requestId}/reject/`, {
        reason,
      }),
    onSuccess: () => {
      toast.success(t("warehouse.requestRejected"));
      void qc.invalidateQueries({ queryKey: ["supply_requests"] });
    },
    onError: (e: Error) => toast.error(t("warehouse.rejectError"), { description: e.message }),
  });

  function rejectReplenishmentRequest(requestId: number) {
    const reason = window.prompt(t("warehouse.rejectionReason"));
    if (reason === null) return;
    if (!reason.trim()) {
      toast.error(t("warehouse.rejectionReasonRequired"));
      return;
    }
    rejectRequest.mutate({ requestId, reason: reason.trim() });
  }

  const transitionTransfer = useMutation({
    mutationFn: async ({ id, action }: { id: number; action: "validate" | "ship" | "receive" }) => {
      if (action !== "receive") return api.post(`inventory/transfers/${id}/${action}/`);
      const transfer = transfers?.find((item) => Number(item.id) === id);
      if (!transfer) throw new Error(t("warehouse.noTransfers"));
      const entered = window.prompt(
        t("warehouse.receivedQuantityPrompt", { quantity: transfer.quantity }),
        String(transfer.quantity),
      );
      if (entered === null) throw new Error(t("warehouse.receiveCancelled"));
      const quantityReceived = Number(entered);
      if (
        !Number.isInteger(quantityReceived) ||
        quantityReceived < 0 ||
        quantityReceived > transfer.quantity
      ) {
        throw new Error(t("warehouse.invalidReceivedQuantity"));
      }
      let varianceReason = "";
      if (quantityReceived !== transfer.quantity) {
        const reason = window.prompt(t("warehouse.varianceReason"));
        if (!reason?.trim()) throw new Error(t("warehouse.varianceReasonRequired"));
        varianceReason = reason.trim();
      }
      return api.post(`inventory/transfers/${id}/${action}/`, {
        quantity_received: quantityReceived,
        variance_reason: varianceReason,
      });
    },
    onSuccess: (_data, variables) => {
      const messageKey = {
        validate: "warehouse.transferValidated",
        ship: "warehouse.transferShipped",
        receive: "warehouse.transferReceived",
      }[variables.action];
      toast.success(t(messageKey));
      void qc.invalidateQueries({ queryKey: ["transfers"] });
      void qc.invalidateQueries({ queryKey: ["product_stock"] });
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["supply_requests"] });
    },
    onError: (e: Error) => toast.error(t("warehouse.transferError"), { description: e.message }),
  });

  const rows = useMemo(() => {
    const map = new Map<
      string,
      { name: string; reference: string; qty: Record<string, number>; total: number }
    >();
    for (const s of stock ?? []) {
      const key = s.product_id;
      const entry = map.get(key) ?? {
        name: s.products?.name ?? "—",
        reference: s.products?.reference ?? "",
        qty: {},
        total: 0,
      };
      entry.qty[s.warehouse_id] = (entry.qty[s.warehouse_id] ?? 0) + s.quantity;
      entry.total += s.quantity;
      map.set(key, entry);
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [stock]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("warehouse.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("warehouse.description")}</p>
        </div>
        {manage && <Button onClick={() => setNewOpen(true)}>{t("warehouse.newLocation")}</Button>}
      </div>

      <div className="panel">
        <div className="border-b p-3 text-sm font-semibold uppercase">
          {t("warehouse.supplyRequests")}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("warehouse.number")}</TableHead>
              <TableHead>{t("warehouse.product")}</TableHead>
              <TableHead className="text-right">{t("warehouse.requested")}</TableHead>
              <TableHead className="text-right">{t("warehouse.missing")}</TableHead>
              <TableHead>{t("warehouse.status")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(requests ?? []).map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-mono text-xs">{r.reference}</TableCell>
                <TableCell>
                  <p className="font-medium">{r.product_name}</p>
                  <p className="text-muted-foreground text-xs">{r.shop_name}</p>
                  {r.refusal_reason && (
                    <p className="text-destructive text-xs">{r.refusal_reason}</p>
                  )}
                  <p className="text-muted-foreground text-xs">{dateTime(r.created_at)}</p>
                </TableCell>
                <TableCell className="text-right">{r.requested_quantity}</TableCell>
                <TableCell className="text-right font-semibold">{r.remaining_quantity}</TableCell>
                <TableCell>
                  <Badge variant={r.status === "completed" ? "default" : "secondary"}>
                    {t(`warehouse.requestStatus.${r.status}`)}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  {manage &&
                    r.remaining_quantity > 0 &&
                    (r.status === "requested" || r.status === "partially_received") && (
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          onClick={() => {
                            setRequestId(String(r.id));
                            setAlloc({});
                          }}
                        >
                          {t("warehouse.transfer")}
                        </Button>
                        {r.status === "requested" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => rejectReplenishmentRequest(r.id)}
                            disabled={rejectRequest.isPending}
                          >
                            {t("warehouse.reject")}
                          </Button>
                        )}
                      </div>
                    )}
                </TableCell>
              </TableRow>
            ))}
            {!requests?.length && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground py-8 text-center">
                  {t("warehouse.noRequests")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="panel overflow-x-auto">
        <div className="border-b p-3 text-sm font-semibold uppercase">
          {t("warehouse.stockByLocation")}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("warehouse.product")}</TableHead>
              {(warehouses ?? []).map((w) => (
                <TableHead key={w.id} className="text-right">
                  {w.name}
                </TableHead>
              ))}
              <TableHead className="text-right">{t("warehouse.total")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.reference + r.name}>
                <TableCell>
                  <p className="font-medium">{r.name}</p>
                  <p className="text-muted-foreground font-mono text-xs">{r.reference}</p>
                </TableCell>
                {(warehouses ?? []).map((w) => (
                  <TableCell key={w.id} className="text-right">
                    {r.qty[w.id] ?? 0}
                  </TableCell>
                ))}
                <TableCell className="text-right font-semibold">{r.total}</TableCell>
              </TableRow>
            ))}
            {!rows.length && (
              <TableRow>
                <TableCell
                  colSpan={(warehouses?.length ?? 0) + 2}
                  className="text-muted-foreground py-8 text-center"
                >
                  {t("warehouse.noStock")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="panel">
        <div className="border-b p-3 text-sm font-semibold uppercase">
          {t("warehouse.transferHistory")}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("warehouse.number")}</TableHead>
              <TableHead>{t("warehouse.lines")}</TableHead>
              <TableHead className="text-right">{t("credits.date")}</TableHead>
              <TableHead>{t("warehouse.status")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(transfers ?? []).map((transfer) => (
              <TableRow key={transfer.id}>
                <TableCell className="font-mono text-xs">{transfer.number}</TableCell>
                <TableCell className="text-sm">
                  {(transfer.transfer_lines ?? []).map((l, i) => (
                    <p key={i}>
                      {l.products?.name} · {l.quantity} {t("warehouse.pieces")} ·{" "}
                      {whName[l.from_warehouse_id]} → {whName[transfer.to_warehouse_id]}
                    </p>
                  ))}
                  {transfer.status === "received" && (
                    <p className="text-muted-foreground text-xs">
                      {t("warehouse.receivedVersusShipped", {
                        shipped: transfer.quantity_shipped,
                        received: transfer.quantity_received ?? 0,
                      })}
                      {transfer.variance_reason ? ` · ${transfer.variance_reason}` : ""}
                    </p>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground text-right text-xs">
                  {dateTime(transfer.created_at)}
                </TableCell>
                <TableCell>
                  <Badge variant={transfer.status === "received" ? "default" : "secondary"}>
                    {t(`warehouse.transferStatus.${transfer.status}`)}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  {hasRole("admin") && transfer.status === "requested" && (
                    <Button
                      size="sm"
                      onClick={() =>
                        transitionTransfer.mutate({
                          id: Number(transfer.id),
                          action: "validate",
                        })
                      }
                      disabled={transitionTransfer.isPending}
                    >
                      {t("warehouse.authorizeTransfer")}
                    </Button>
                  )}
                  {hasRole("stock") && transfer.status === "validated" && (
                    <Button
                      size="sm"
                      onClick={() =>
                        transitionTransfer.mutate({ id: Number(transfer.id), action: "ship" })
                      }
                      disabled={transitionTransfer.isPending}
                    >
                      {t("warehouse.shipTransfer")}
                    </Button>
                  )}
                  {hasRole("stock") && transfer.status === "shipped" && (
                    <Button
                      size="sm"
                      onClick={() =>
                        transitionTransfer.mutate({ id: Number(transfer.id), action: "receive" })
                      }
                      disabled={transitionTransfer.isPending}
                    >
                      {t("warehouse.receiveTransfer")}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!transfers?.length && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                  {t("warehouse.noTransfers")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={newOpen} onOpenChange={setNewOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("warehouse.newLocation")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>{t("warehouse.name")}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>{t("warehouse.type")}</Label>
              <Select
                value={kind}
                onValueChange={(value) => {
                  setKind(value);
                  if (value !== "boutique") setAuthorizedUsers([]);
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="entrepot">{t("warehouse.warehouse")}</SelectItem>
                  {hasRole("admin") && (
                    <SelectItem value="boutique">{t("warehouse.shop")}</SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("warehouse.address")}</Label>
              <Input value={address} onChange={(e) => setAddress(e.target.value)} />
            </div>
            {kind === "boutique" && hasRole("admin") && (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">{t("warehouse.shopSellers")}</legend>
                {salesUsers?.map((user) => {
                  const id = String(user.id);
                  const label = `${user.first_name} ${user.last_name}`.trim() || user.username;
                  return (
                    <label key={user.id} className="flex min-h-11 items-center gap-3 text-sm">
                      <Checkbox
                        checked={authorizedUsers.includes(id)}
                        onCheckedChange={(checked) =>
                          setAuthorizedUsers((current) =>
                            checked
                              ? [...current, id]
                              : current.filter((selectedId) => selectedId !== id),
                          )
                        }
                      />
                      {label}
                    </label>
                  );
                })}
                {!salesUsers?.length && (
                  <p className="text-muted-foreground text-sm">{t("warehouse.noActiveSellers")}</p>
                )}
              </fieldset>
            )}
          </div>
          <DialogFooter>
            <Button
              onClick={() => createWarehouse.mutate()}
              disabled={
                !name.trim() ||
                createWarehouse.isPending ||
                (kind === "boutique" &&
                  (salesUsers === undefined ||
                    salesUsers.length === 0 ||
                    authorizedUsers.length === 0))
              }
            >
              {t("warehouse.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!requestId} onOpenChange={(o) => !o && setRequestId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("warehouse.transferToShop")}</DialogTitle>
          </DialogHeader>
          {activeRequest && (
            <div className="space-y-3">
              <p className="text-sm">
                <span className="font-medium">{activeRequest.product_name}</span> ·{" "}
                {t("warehouse.requiredPieces", {
                  count: formatNumber(activeRequest.remaining_quantity),
                })}
              </p>
              {sources.map((s) => (
                <div key={s.warehouse_id} className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{whName[s.warehouse_id]}</p>
                    <p className="text-muted-foreground text-xs">
                      {t("warehouse.available", { count: formatNumber(s.quantity) })}
                    </p>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    max={s.quantity}
                    className="w-24 text-right"
                    value={alloc[s.warehouse_id] ?? ""}
                    onChange={(e) =>
                      setAlloc((prev) => ({ ...prev, [s.warehouse_id]: e.target.value }))
                    }
                  />
                </div>
              ))}
              {!sources.length && (
                <p className="text-destructive text-sm">{t("warehouse.noSourceStock")}</p>
              )}
              <p className="text-sm font-semibold">
                {t("warehouse.transferTotal", {
                  current: allocTotal,
                  required: activeRequest.remaining_quantity,
                })}
              </p>
            </div>
          )}
          <DialogFooter>
            <Button
              onClick={() => doTransfer.mutate()}
              disabled={
                !activeRequest ||
                allocTotal !== activeRequest.remaining_quantity ||
                doTransfer.isPending
              }
            >
              {hasRole("stock") && !hasRole("admin")
                ? t("warehouse.requestTransfer")
                : t("warehouse.validateTransfer")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
