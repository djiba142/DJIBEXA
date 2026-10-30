import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowDownToLine, ArrowUpFromLine, CircleDollarSign, Truck } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

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
import { money, shortDate } from "@/lib/format";
import { useLocale } from "@/lib/locale";

type Supplier = { id: number; name: string };
type FinancialAccount = { id: number; name: string; currency: string; status: string };
type Location = { id: number; name: string; location_type: string; is_active: boolean };
type ExternalPurchase = {
  id: number;
  reference: string;
  supplier: number;
  supplier_name: string;
  sale: number;
  sale_invoice: string | null;
  item_name: string;
  item_reference: string;
  quantity: number;
  total_cost: string;
  total_paid: string;
  balance_due: string;
  payment_status: "unpaid" | "partial" | "paid";
  purchase_date: string;
  due_date: string | null;
  delivery_mode: "direct" | "warehouse";
  status: "confirmed" | "cancelled";
  received_quantity: number;
  delivered_quantity: number;
};
type ExternalPayment = {
  id: number;
  reference: string;
  supplier: number;
  supplier_name: string;
  amount: string;
  payment_method: string;
  payment_date: string;
  allocations: { purchase: number; reference: string; item_name: string; amount: string }[];
};

function numeric(value: string | number | null | undefined) {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function SupplierDebtsTab() {
  const { t } = useLocale();
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const canManageStock = hasRole("stock") || isAdmin;
  const queryClient = useQueryClient();
  const [supplierFilter, setSupplierFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [accountId, setAccountId] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 16));
  const [paymentProof, setPaymentProof] = useState("");
  const [movementPurchase, setMovementPurchase] = useState<ExternalPurchase | null>(null);
  const [movementType, setMovementType] = useState<"received" | "delivered" | "direct_delivery">(
    "received",
  );
  const [movementQuantity, setMovementQuantity] = useState("");
  const [movementLocationId, setMovementLocationId] = useState("");
  const [movementProof, setMovementProof] = useState("");

  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: () => api.list<Supplier>("suppliers/"),
  });
  const accountsQuery = useQuery({
    queryKey: ["financial-accounts"],
    queryFn: () => api.list<FinancialAccount>("finance/accounts/"),
    enabled: isAdmin && paymentDialogOpen,
  });
  const locationsQuery = useQuery({
    queryKey: ["external-purchase-locations"],
    queryFn: () => api.list<Location>("locations/"),
    enabled: movementPurchase?.delivery_mode === "warehouse",
  });
  const purchaseParams =
    supplierFilter === "all" ? undefined : { supplier: Number(supplierFilter) };
  const purchasesQuery = useQuery({
    queryKey: ["external-purchases", supplierFilter],
    queryFn: () => api.list<ExternalPurchase>("external-purchases/", purchaseParams),
  });
  const summaryQuery = useQuery({
    queryKey: ["external-purchase-summary", supplierFilter],
    queryFn: () =>
      api.get<{
        purchase_total: string;
        total_paid: string;
        balance_due: string;
        purchase_count: number;
      }>("external-purchases/summary/", purchaseParams),
  });
  const paymentsQuery = useQuery({
    queryKey: ["external-purchase-payments", supplierFilter],
    queryFn: () => api.list<ExternalPayment>("external-payments/", purchaseParams),
  });

  const purchases = useMemo(() => purchasesQuery.data ?? [], [purchasesQuery.data]);
  const suppliers = suppliersQuery.data ?? [];
  const accounts = (accountsQuery.data ?? []).filter(
    (account) => account.status === "active" && account.currency === "GNF",
  );
  const locations = (locationsQuery.data ?? []).filter(
    (location) =>
      location.is_active &&
      ["warehouse", "shop", "storage", "other"].includes(location.location_type),
  );
  const visiblePurchases = useMemo(
    () =>
      purchases.filter((purchase) => {
        const term = search.trim().toLocaleLowerCase();
        return (
          (statusFilter === "all" || purchase.payment_status === statusFilter) &&
          (!term ||
            [
              purchase.item_name,
              purchase.item_reference,
              purchase.reference,
              purchase.supplier_name,
              purchase.sale_invoice ?? "",
            ].some((value) => value.toLocaleLowerCase().includes(term)))
        );
      }),
    [purchases, search, statusFilter],
  );
  const selectedPurchases = useMemo(
    () =>
      visiblePurchases.filter(
        (purchase) => selectedIds.includes(purchase.id) && numeric(purchase.balance_due) > 0,
      ),
    [visiblePurchases, selectedIds],
  );
  const selectedBalance = selectedPurchases.reduce(
    (total, purchase) => total + numeric(purchase.balance_due),
    0,
  );

  const createPayment = useMutation({
    mutationFn: async () => {
      const amount = numeric(paymentAmount);
      if (!selectedPurchases.length) throw new Error(t("externalPurchases.selectPurchases"));
      if (!Number.isFinite(amount) || amount <= 0 || amount > selectedBalance) {
        throw new Error(t("externalPurchases.paymentAmountInvalid"));
      }
      if (!accountId) throw new Error(t("externalPurchases.chooseAccount"));
      const suppliersForPayment = new Set(selectedPurchases.map((purchase) => purchase.supplier));
      if (suppliersForPayment.size !== 1) throw new Error(t("externalPurchases.oneSupplierOnly"));
      return api.post<ExternalPayment>(
        "external-payments/",
        {
          supplier: selectedPurchases[0].supplier,
          purchase_ids: selectedPurchases.map((purchase) => purchase.id),
          amount: amount.toFixed(2),
          payment_method: paymentMethod,
          financial_account: Number(accountId),
          payment_date: new Date(paymentDate).toISOString(),
          proof_reference: paymentProof.trim(),
        },
        { "Idempotency-Key": crypto.randomUUID() },
      );
    },
    onSuccess: async (payment) => {
      toast.success(t("externalPurchases.paymentSaved"), {
        description: `${payment.reference} · ${money(payment.amount)}`,
      });
      setPaymentDialogOpen(false);
      setSelectedIds([]);
      setPaymentAmount("");
      setPaymentProof("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["external-purchases"] }),
        queryClient.invalidateQueries({ queryKey: ["external-purchase-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["external-purchase-payments"] }),
        queryClient.invalidateQueries({ queryKey: ["financial-accounts"] }),
      ]);
    },
    onError: (error: Error) =>
      toast.error(t("externalPurchases.paymentFailed"), { description: error.message }),
  });

  const saveMovement = useMutation({
    mutationFn: async () => {
      if (!movementPurchase) throw new Error(t("externalPurchases.purchaseMissing"));
      const quantity = Number(movementQuantity);
      if (!Number.isInteger(quantity) || quantity <= 0) {
        throw new Error(t("externalPurchases.quantityInvalid"));
      }
      const locationRequired = movementType !== "direct_delivery";
      if (locationRequired && !movementLocationId) {
        throw new Error(t("externalPurchases.chooseLocation"));
      }
      return api.post(
        `external-purchases/${movementPurchase.id}/movements/`,
        {
          movement_type: movementType,
          quantity,
          ...(locationRequired ? { location: Number(movementLocationId) } : {}),
          proof_reference: movementProof.trim(),
        },
        { "Idempotency-Key": crypto.randomUUID() },
      );
    },
    onSuccess: async () => {
      toast.success(t("externalPurchases.movementSaved"));
      setMovementPurchase(null);
      setMovementLocationId("");
      setMovementProof("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["external-purchases"] }),
        queryClient.invalidateQueries({ queryKey: ["external-purchase-summary"] }),
      ]);
    },
    onError: (error: Error) =>
      toast.error(t("externalPurchases.movementFailed"), { description: error.message }),
  });

  function togglePurchase(purchase: ExternalPurchase, checked: boolean) {
    setSelectedIds((current) => {
      if (!checked) return current.filter((id) => id !== purchase.id);
      if (
        current.some(
          (id) => purchases.find((item) => item.id === id)?.supplier !== purchase.supplier,
        )
      ) {
        toast.error(t("externalPurchases.oneSupplierOnly"));
        return current;
      }
      return [...current, purchase.id];
    });
  }

  function openPayment() {
    if (!selectedPurchases.length) {
      toast.error(t("externalPurchases.selectPurchases"));
      return;
    }
    setPaymentAmount(selectedBalance.toFixed(2));
    setPaymentDialogOpen(true);
  }

  function openMovement(
    purchase: ExternalPurchase,
    type: "received" | "delivered" | "direct_delivery",
  ) {
    const remaining =
      type === "received"
        ? purchase.quantity - purchase.received_quantity
        : type === "direct_delivery"
          ? purchase.quantity - purchase.delivered_quantity
          : purchase.received_quantity - purchase.delivered_quantity;
    setMovementPurchase(purchase);
    setMovementType(type);
    setMovementQuantity(String(remaining));
    setMovementLocationId("");
    setMovementProof("");
  }

  return (
    <div className="space-y-6">
      <header>
        <div>
          <h2 className="text-xl font-semibold">{t("credits.supplierDebtsHeading")}</h2>
          <p className="text-muted-foreground mt-1 max-w-3xl text-sm">
            {t("credits.supplierDebtsDescription")}
          </p>
        </div>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="panel p-4">
          <p className="text-muted-foreground text-sm">{t("externalPurchases.purchaseTotal")}</p>
          <p className="mt-2 text-xl font-semibold">{money(summaryQuery.data?.purchase_total)}</p>
        </div>
        <div className="panel p-4">
          <p className="text-muted-foreground text-sm">{t("externalPurchases.paidTotal")}</p>
          <p className="mt-2 text-xl font-semibold">{money(summaryQuery.data?.total_paid)}</p>
        </div>
        <div className="panel border-amber-200 p-4">
          <p className="text-muted-foreground text-sm">{t("externalPurchases.balanceDue")}</p>
          <p className="mt-2 text-xl font-semibold text-amber-700">
            {money(summaryQuery.data?.balance_due)}
          </p>
        </div>
        <div className="panel p-4">
          <p className="text-muted-foreground text-sm">{t("externalPurchases.purchaseCount")}</p>
          <p className="mt-2 text-xl font-semibold">{summaryQuery.data?.purchase_count ?? 0}</p>
        </div>
      </section>

      <section className="panel space-y-4 p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold">{t("externalPurchases.accountTitle")}</h2>
            <p className="text-muted-foreground text-sm">
              {t("externalPurchases.accountDescription")}
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="relative">
              <Input
                aria-label={t("credits.supplierSearch")}
                placeholder={t("credits.supplierSearch")}
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setSelectedIds([]);
                }}
              />
            </div>
            <Select
              value={supplierFilter}
              onValueChange={(value) => {
                setSupplierFilter(value);
                setSelectedIds([]);
              }}
            >
              <SelectTrigger aria-label={t("externalPurchases.supplier")}>
                <SelectValue placeholder={t("externalPurchases.allSuppliers")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("externalPurchases.allSuppliers")}</SelectItem>
                {suppliers.map((supplier) => (
                  <SelectItem key={supplier.id} value={String(supplier.id)}>
                    {supplier.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={statusFilter}
              onValueChange={(value) => {
                setStatusFilter(value);
                setSelectedIds([]);
              }}
            >
              <SelectTrigger aria-label={t("credits.supplierStatusFilter")}>
                <SelectValue placeholder={t("credits.supplierStatusFilter")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("credits.allSupplierStatuses")}</SelectItem>
                <SelectItem value="unpaid">{t("externalPurchases.status.unpaid")}</SelectItem>
                <SelectItem value="partial">{t("externalPurchases.status.partial")}</SelectItem>
                <SelectItem value="paid">{t("externalPurchases.status.paid")}</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex justify-end">
              {isAdmin && (
                <Button
                  variant="outline"
                  disabled={!selectedPurchases.length}
                  onClick={openPayment}
                >
                  <CircleDollarSign className="mr-2 size-4" />
                  {t("externalPurchases.paySelected")}
                </Button>
              )}
            </div>
          </div>
        </div>

        {suppliersQuery.isError && (
          <p role="alert" className="text-destructive text-sm">
            {t("externalPurchases.referencesLoadFailed")}
          </p>
        )}
        {summaryQuery.isError && (
          <p role="alert" className="text-destructive text-sm">
            {t("externalPurchases.loadFailed")}: {summaryQuery.error.message}
          </p>
        )}
        {purchasesQuery.isError ? (
          <p className="text-destructive text-sm">{t("externalPurchases.loadFailed")}</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {isAdmin && <TableHead className="w-10" />}
                  <TableHead>{t("externalPurchases.item")}</TableHead>
                  <TableHead>{t("externalPurchases.supplier")}</TableHead>
                  <TableHead>{t("externalPurchases.invoice")}</TableHead>
                  <TableHead>{t("externalPurchases.purchaseDate")}</TableHead>
                  <TableHead>{t("externalPurchases.dueDate")}</TableHead>
                  <TableHead>{t("externalPurchases.paymentStatus")}</TableHead>
                  <TableHead>{t("externalPurchases.delivery")}</TableHead>
                  <TableHead className="text-right">{t("externalPurchases.totalCost")}</TableHead>
                  <TableHead className="text-right">{t("externalPurchases.paidTotal")}</TableHead>
                  <TableHead className="text-right">{t("externalPurchases.balanceDue")}</TableHead>
                  <TableHead>{t("externalPurchases.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visiblePurchases.map((purchase) => {
                  const isSelected = selectedIds.includes(purchase.id);
                  const deliveredRemaining =
                    purchase.delivery_mode === "direct"
                      ? purchase.quantity - purchase.delivered_quantity
                      : purchase.received_quantity - purchase.delivered_quantity;
                  return (
                    <TableRow key={purchase.id}>
                      {isAdmin && (
                        <TableCell>
                          <Checkbox
                            aria-label={`${t("externalPurchases.selectPurchase")} ${purchase.reference}`}
                            checked={isSelected}
                            disabled={
                              purchase.status !== "confirmed" || numeric(purchase.balance_due) <= 0
                            }
                            onCheckedChange={(checked) =>
                              togglePurchase(purchase, checked === true)
                            }
                          />
                        </TableCell>
                      )}
                      <TableCell>
                        <div className="font-medium">{purchase.item_name}</div>
                        <div className="text-muted-foreground font-mono text-xs">
                          {purchase.item_reference || purchase.reference}
                        </div>
                      </TableCell>
                      <TableCell>{purchase.supplier_name}</TableCell>
                      <TableCell>
                        {purchase.sale_invoice ? (
                          <Link
                            className="text-primary underline-offset-4 hover:underline"
                            to="/ventes/$saleId"
                            params={{ saleId: String(purchase.sale) }}
                          >
                            {purchase.sale_invoice}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell>{shortDate(purchase.purchase_date)}</TableCell>
                      <TableCell>
                        {purchase.due_date ? shortDate(purchase.due_date) : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={purchase.payment_status === "paid" ? "default" : "secondary"}
                        >
                          {t(`externalPurchases.status.${purchase.payment_status}`)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {purchase.delivery_mode === "direct"
                          ? `${t("externalPurchases.direct")} · ${purchase.delivered_quantity}/${purchase.quantity}`
                          : `${purchase.delivered_quantity}/${purchase.quantity}`}
                      </TableCell>
                      <TableCell className="text-right">{money(purchase.total_cost)}</TableCell>
                      <TableCell className="text-right">{money(purchase.total_paid)}</TableCell>
                      <TableCell className="text-right font-medium">
                        {money(purchase.balance_due)}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {canManageStock &&
                            purchase.status === "confirmed" &&
                            purchase.delivery_mode === "direct" &&
                            deliveredRemaining > 0 && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openMovement(purchase, "direct_delivery")}
                              >
                                <Truck className="mr-1 size-3" />
                                {t("externalPurchases.markDelivered")}
                              </Button>
                            )}
                          {canManageStock &&
                            purchase.status === "confirmed" &&
                            purchase.delivery_mode === "warehouse" &&
                            purchase.received_quantity < purchase.quantity && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openMovement(purchase, "received")}
                              >
                                <ArrowDownToLine className="mr-1 size-3" />
                                {t("externalPurchases.receive")}
                              </Button>
                            )}
                          {canManageStock &&
                            purchase.status === "confirmed" &&
                            purchase.delivery_mode === "warehouse" &&
                            deliveredRemaining > 0 && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openMovement(purchase, "delivered")}
                              >
                                <ArrowUpFromLine className="mr-1 size-3" />
                                {t("externalPurchases.deliver")}
                              </Button>
                            )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {visiblePurchases.length === 0 && !purchasesQuery.isLoading && (
                  <TableRow>
                    <TableCell
                      colSpan={isAdmin ? 12 : 11}
                      className="text-muted-foreground h-24 text-center"
                    >
                      {t("externalPurchases.empty")}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section className="panel space-y-4 p-4 sm:p-5">
        <div>
          <h2 className="font-semibold">{t("externalPurchases.paymentHistory")}</h2>
          <p className="text-muted-foreground text-sm">
            {t("externalPurchases.paymentHistoryDescription")}
          </p>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("externalPurchases.paymentReference")}</TableHead>
                <TableHead>{t("externalPurchases.supplier")}</TableHead>
                <TableHead>{t("externalPurchases.paymentDate")}</TableHead>
                <TableHead>{t("externalPurchases.allocations")}</TableHead>
                <TableHead className="text-right">{t("externalPurchases.amount")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(paymentsQuery.data ?? []).map((payment) => (
                <TableRow key={payment.id}>
                  <TableCell className="font-mono text-xs">{payment.reference}</TableCell>
                  <TableCell>{payment.supplier_name}</TableCell>
                  <TableCell>{shortDate(payment.payment_date)}</TableCell>
                  <TableCell>
                    {payment.allocations.map((allocation) => allocation.reference).join(", ") ||
                      "—"}
                  </TableCell>
                  <TableCell className="text-right font-medium">{money(payment.amount)}</TableCell>
                </TableRow>
              ))}
              {(paymentsQuery.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-muted-foreground h-16 text-center">
                    {t("externalPurchases.noPayments")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <Dialog open={paymentDialogOpen} onOpenChange={setPaymentDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("externalPurchases.groupPayment")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg bg-muted p-3 text-sm">
              {t("externalPurchases.selectedDue")}: <strong>{money(selectedBalance)}</strong>
            </div>
            <div className="space-y-2">
              <Label>{t("externalPurchases.amount")}</Label>
              <Input
                type="number"
                min="0.01"
                max={selectedBalance}
                step="0.01"
                value={paymentAmount}
                onChange={(event) => setPaymentAmount(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("externalPurchases.financialAccount")}</Label>
              <Select value={accountId} onValueChange={setAccountId}>
                <SelectTrigger>
                  <SelectValue placeholder={t("externalPurchases.chooseAccount")} />
                </SelectTrigger>
                <SelectContent>
                  {accounts.map((account) => (
                    <SelectItem key={account.id} value={String(account.id)}>
                      {account.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>{t("externalPurchases.paymentMethod")}</Label>
                <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">{t("externalPurchases.cash")}</SelectItem>
                    <SelectItem value="mobile_money">
                      {t("externalPurchases.mobileMoney")}
                    </SelectItem>
                    <SelectItem value="bank_transfer">
                      {t("externalPurchases.bankTransfer")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>{t("externalPurchases.paymentDate")}</Label>
                <Input
                  type="datetime-local"
                  value={paymentDate}
                  onChange={(event) => setPaymentDate(event.target.value)}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t("externalPurchases.proofReference")}</Label>
              <Input
                value={paymentProof}
                onChange={(event) => setPaymentProof(event.target.value)}
                maxLength={255}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPaymentDialogOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={createPayment.isPending || accountsQuery.isLoading}
              onClick={() => createPayment.mutate()}
            >
              {createPayment.isPending
                ? t("externalPurchases.saving")
                : t("externalPurchases.recordPayment")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={movementPurchase !== null}
        onOpenChange={(open) => !open && setMovementPurchase(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t(`externalPurchases.movement.${movementType}`)}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {movementPurchase && (
              <p className="text-muted-foreground text-sm">
                {movementPurchase.item_name} · {movementPurchase.reference}
              </p>
            )}
            <div className="space-y-2">
              <Label>{t("externalPurchases.quantity")}</Label>
              <Input
                type="number"
                min="1"
                value={movementQuantity}
                onChange={(event) => setMovementQuantity(event.target.value)}
              />
            </div>
            {movementType !== "direct_delivery" && (
              <div className="space-y-2">
                <Label>{t("externalPurchases.location")}</Label>
                <Select value={movementLocationId} onValueChange={setMovementLocationId}>
                  <SelectTrigger>
                    <SelectValue placeholder={t("externalPurchases.chooseLocation")} />
                  </SelectTrigger>
                  <SelectContent>
                    {locations.map((location) => (
                      <SelectItem key={location.id} value={String(location.id)}>
                        {location.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label>{t("externalPurchases.proofReference")}</Label>
              <Input
                value={movementProof}
                onChange={(event) => setMovementProof(event.target.value)}
                maxLength={255}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMovementPurchase(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={saveMovement.isPending || locationsQuery.isLoading}
              onClick={() => saveMovement.mutate()}
            >
              {saveMovement.isPending
                ? t("externalPurchases.saving")
                : t("externalPurchases.confirmMovement")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
