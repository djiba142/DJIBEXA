import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, Clock3, FileDown, MessageCircle, Search, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { SupplierDebtsTab } from "@/components/credits/SupplierDebtsTab";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { buildDocumentPdf, shareOnWhatsApp } from "@/lib/document-pdf";
import { money, shortDate } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/credits")({
  head: () => ({
    meta: [
      { title: "Crédits — ERP DJIBEXA" },
      {
        name: "description",
        content: "Suivi distinct des créances clients et des dettes fournisseurs.",
      },
    ],
  }),
  component: CustomerCreditsPage,
});

type CreditSummary = {
  customer_id: number;
  customer_name: string;
  customer_phone: string;
  sales_count: number;
  total_credit: number | string;
  total_paid: number | string;
  balance: number | string;
  last_payment: string | null;
  status: "settled" | "partial" | "unpaid";
};

type CreditDetail = {
  customer: { id: number; full_name: string; phone: string; email: string };
  currency: string;
  sales_count: number;
  total_credit: number | string;
  total_paid: number | string;
  balance: number | string;
  status: "settled" | "partial" | "unpaid";
  sales: {
    sale_id: number;
    invoice_number: string | null;
    date: string;
    total_credit: number | string;
    total_paid: number | string;
    balance: number | string;
  }[];
  payments: {
    id: number;
    amount: number | string;
    payment_method: string;
    reference: string;
    payment_date: string;
    created_by_name: string;
    allocations: { sale: number; invoice_number: string | null; amount: number | string }[];
  }[];
};

const paymentMethods = [
  { value: "cash", labelKey: "credits.cash" },
  { value: "mobile_money", labelKey: "credits.mobileMoney" },
  { value: "bank_transfer", labelKey: "credits.bankTransfer" },
];

function amount(value: number | string | null | undefined) {
  return Number(value ?? 0);
}

function paymentMethodLabel(value: string, t: (key: string) => string) {
  const method = paymentMethods.find((item) => item.value === value);
  return method ? t(method.labelKey) : value;
}

function CustomerCreditsPage() {
  const { language, t } = useLocale();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const canViewSupplierDebts = can("purchases.view");
  const [activeTab, setActiveTab] = useState(() => {
    const requestedTab =
      typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("tab");
    return requestedTab === "suppliers" && canViewSupplierDebts ? "suppliers" : "customers";
  });
  const [search, setSearch] = useState("");
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  const [paymentCustomer, setPaymentCustomer] = useState<CreditSummary | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const [paymentRequestId, setPaymentRequestId] = useState("");

  useEffect(() => {
    const customerId = Number(new URLSearchParams(window.location.search).get("customer"));
    if (Number.isInteger(customerId) && customerId > 0) setSelectedCustomerId(customerId);
  }, []);

  const creditsQuery = useQuery({
    queryKey: ["credits", search],
    queryFn: () => api.get<CreditSummary[]>("payments/credits/", { search }),
  });
  const detailQuery = useQuery({
    queryKey: ["credit-detail", selectedCustomerId],
    queryFn: () => api.get<CreditDetail>(`payments/customer/${selectedCustomerId}/credits/`),
    enabled: selectedCustomerId !== null,
  });
  const credits = useMemo(() => creditsQuery.data ?? [], [creditsQuery.data]);
  const totals = useMemo(
    () =>
      credits.reduce(
        (result, credit) => ({
          receivables: result.receivables + amount(credit.total_credit),
          received: result.received + amount(credit.total_paid),
          balance: result.balance + amount(credit.balance),
          customers: result.customers + (amount(credit.balance) > 0 ? 1 : 0),
        }),
        { receivables: 0, received: 0, balance: 0, customers: 0 },
      ),
    [credits],
  );

  const paymentMutation = useMutation({
    mutationFn: async () => {
      if (!paymentCustomer) throw new Error(t("credits.selectCustomer"));
      const value = Number(paymentAmount);
      if (!Number.isFinite(value) || value <= 0) throw new Error(t("credits.enterPositiveAmount"));
      if (value > amount(paymentCustomer.balance)) {
        throw new Error(t("credits.paymentExceedsBalance"));
      }
      return api.post<{ id: number; reference: string }>(
        "payments/",
        {
          customer: paymentCustomer.customer_id,
          sale: null,
          amount: value.toFixed(2),
          payment_method: paymentMethod,
          reference: reference.trim(),
          payment_date: new Date(`${paymentDate}T12:00:00`).toISOString(),
        },
        { "Idempotency-Key": paymentRequestId },
      );
    },
    onSuccess: async (payment: { id: number; reference: string }) => {
      toast.success(t("credits.paymentSaved"), {
        description: t("credits.accountUpdated"),
      });
      const customerId = paymentCustomer?.customer_id;
      try {
        const receipt = await api.get<{
          payment_id: number;
          reference: string;
          customer: string;
          amount: string;
          payment_method: string;
          payment_date: string;
          created_by: string;
          allocations: { invoice_number: string | null; amount: string }[];
        }>(`payments/${payment.id}/receipt/`);
        const pdf = await buildDocumentPdf({
          kind: t("credits.payment"),
          number: receipt.reference,
          date: shortDate(receipt.payment_date),
          parties: [
            { label: t("credits.customer"), value: receipt.customer },
            {
              label: t("credits.method"),
              value: paymentMethodLabel(receipt.payment_method, t),
            },
            { label: t("credits.recordedBy"), value: receipt.created_by || "—" },
            {
              label: t("credits.allocations"),
              value:
                receipt.allocations
                  .map((item) => item.invoice_number || t("credits.purchase"))
                  .join(", ") || t("credits.customer"),
            },
          ],
          lines: [{ label: t("credits.paymentsReceived"), qty: 1, price: amount(receipt.amount) }],
          total: amount(receipt.amount),
        });
        const receiptUrl = URL.createObjectURL(pdf);
        const receiptLink = document.createElement("a");
        receiptLink.href = receiptUrl;
        receiptLink.download = `recu-${receipt.reference}.pdf`;
        receiptLink.click();
        window.setTimeout(() => URL.revokeObjectURL(receiptUrl), 5000);
      } catch (error) {
        toast.error(t("credits.receiptUnavailable"), {
          description: error instanceof Error ? error.message : t("credits.receiptCreationError"),
        });
      }
      setPaymentCustomer(null);
      setPaymentAmount("");
      setReference("");
      await queryClient.invalidateQueries({ queryKey: ["credits"] });
      if (customerId) {
        await queryClient.invalidateQueries({ queryKey: ["credit-detail", customerId] });
        setSelectedCustomerId(customerId);
      }
    },
    onError: (error: Error) =>
      toast.error(t("credits.paymentImpossible"), { description: error.message }),
  });

  async function createStatementPdf(detail: CreditDetail) {
    return buildDocumentPdf({
      kind: t("credits.statementTitle"),
      number: `CLIENT-${detail.customer.id}`,
      date: new Date().toLocaleDateString(language === "zh" ? "zh-CN" : language),
      parties: [
        { label: t("credits.customer"), value: detail.customer.full_name },
        { label: t("credits.phone"), value: detail.customer.phone },
        { label: t("credits.totalCredit"), value: money(detail.total_credit) },
        { label: t("credits.totalPaid"), value: money(detail.total_paid) },
        { label: t("credits.remainingToPay"), value: money(detail.balance) },
      ],
      lines: detail.sales.map((sale) => ({
        label: sale.invoice_number || `Vente #${sale.sale_id}`,
        qty: 1,
        price: amount(sale.total_credit),
        sub: `${shortDate(sale.date)} · ${t("credits.paid")} ${money(sale.total_paid)} · ${t("credits.balance")} ${money(sale.balance)}`,
      })),
      total: amount(detail.balance),
      verifyUrl: `${window.location.origin}/credits?customer=${detail.customer.id}`,
      footer: t("credits.statementFooter", { currency: detail.currency || "GNF" }),
    });
  }

  async function printStatement(detail: CreditDetail) {
    try {
      const pdf = await createStatementPdf(detail);
      const url = URL.createObjectURL(pdf);
      const link = document.createElement("a");
      link.href = url;
      link.download = `etat-compte-${detail.customer.id}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (error) {
      toast.error(t("credits.statementUnavailable"), {
        description: error instanceof Error ? error.message : t("credits.pdfCreationError"),
      });
    }
  }

  async function shareStatement(detail: CreditDetail) {
    try {
      const pdf = await createStatementPdf(detail);
      const message = `${detail.customer.full_name} — ${t("credits.statementTitle")}. ${t("credits.remainingToPay")} : ${money(detail.balance)}.`;
      await shareOnWhatsApp(
        pdf,
        `etat-compte-${detail.customer.id}.pdf`,
        message,
        detail.customer.phone,
      );
    } catch (error) {
      toast.error(t("credits.whatsappShareError"), {
        description: error instanceof Error ? error.message : t("credits.shareError"),
      });
    }
  }

  const activeCredit = paymentCustomer
    ? (credits.find((credit) => credit.customer_id === paymentCustomer.customer_id) ??
      paymentCustomer)
    : null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold uppercase">{t("credits.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("credits.description")}</p>
        </div>
        {activeTab === "customers" && (
          <Button
            variant="outline"
            onClick={() => creditsQuery.refetch()}
            disabled={creditsQuery.isFetching}
          >
            {t("credits.refresh")}
          </Button>
        )}
      </header>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 sm:flex sm:w-fit">
          <TabsTrigger value="customers">{t("credits.customerTab")}</TabsTrigger>
          {canViewSupplierDebts && (
            <TabsTrigger value="suppliers">{t("credits.supplierDebtsTab")}</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="customers" className="space-y-6">
          <p className="text-muted-foreground text-sm">{t("credits.customerTabDescription")}</p>
          {creditsQuery.isError && (
            <div
              role="alert"
              className="rounded-md border border-destructive/40 p-4 text-sm text-destructive"
            >
              {t("credits.loadError")}: {creditsQuery.error.message}
            </div>
          )}

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard
              label={t("credits.totalReceivables")}
              value={money(totals.receivables)}
              icon={WalletCards}
            />
            <SummaryCard
              label={t("credits.debtors")}
              value={String(totals.customers)}
              icon={Search}
            />
            <SummaryCard
              label={t("credits.paymentsReceived")}
              value={money(totals.received)}
              icon={CheckCircle2}
            />
            <SummaryCard
              label={t("credits.remaining")}
              value={money(totals.balance)}
              icon={Clock3}
            />
          </section>

          <div className="relative max-w-xl">
            <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              aria-label={t("credits.searchLabel")}
              placeholder={t("credits.searchPlaceholder")}
              className="pl-9"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <div className="panel overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("credits.customer")}</TableHead>
                  <TableHead>{t("credits.phone")}</TableHead>
                  <TableHead className="text-right">{t("credits.purchases")}</TableHead>
                  <TableHead className="text-right">{t("credits.totalCredit")}</TableHead>
                  <TableHead className="text-right">{t("credits.paid")}</TableHead>
                  <TableHead className="text-right">{t("credits.balance")}</TableHead>
                  <TableHead>{t("credits.lastPayment")}</TableHead>
                  <TableHead>{t("credits.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {creditsQuery.isLoading ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                      {t("credits.loading")}
                    </TableCell>
                  </TableRow>
                ) : (
                  credits.map((credit) => (
                    <TableRow key={credit.customer_id}>
                      <TableCell className="min-w-36 font-medium">{credit.customer_name}</TableCell>
                      <TableCell>{credit.customer_phone || "—"}</TableCell>
                      <TableCell className="text-right">{credit.sales_count}</TableCell>
                      <TableCell className="text-right">{money(credit.total_credit)}</TableCell>
                      <TableCell className="text-right">{money(credit.total_paid)}</TableCell>
                      <TableCell className="text-right font-semibold">
                        {money(credit.balance)}
                      </TableCell>
                      <TableCell>
                        {credit.last_payment ? shortDate(credit.last_payment) : "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex min-w-52 flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setSelectedCustomerId(credit.customer_id)}
                          >
                            {t("credits.details")}
                          </Button>
                          {amount(credit.balance) > 0 && (
                            <Button
                              size="sm"
                              onClick={() => {
                                setPaymentCustomer(credit);
                                setPaymentRequestId(crypto.randomUUID());
                              }}
                            >
                              {t("credits.payment")}
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
                {!creditsQuery.isLoading && credits.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                      {search ? t("credits.noSearchResults") : t("credits.none")}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
        {canViewSupplierDebts && (
          <TabsContent value="suppliers" className="space-y-6">
            <p className="text-muted-foreground text-sm">{t("credits.supplierTabDescription")}</p>
            <SupplierDebtsTab />
          </TabsContent>
        )}
      </Tabs>

      <Dialog
        open={selectedCustomerId !== null}
        onOpenChange={(open) => !open && setSelectedCustomerId(null)}
      >
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {detailQuery.data?.customer.full_name ?? t("credits.accountDetails")}
            </DialogTitle>
          </DialogHeader>
          {detailQuery.isLoading ? (
            <p className="py-8 text-center text-muted-foreground">{t("credits.loadingAccount")}</p>
          ) : detailQuery.isError ? (
            <p role="alert" className="py-8 text-center text-destructive">
              {t("credits.accountLoadError")}: {detailQuery.error.message}
            </p>
          ) : detailQuery.data ? (
            <CreditDetailPanel
              detail={detailQuery.data}
              onPrint={() => void printStatement(detailQuery.data!)}
              onShare={() => void shareStatement(detailQuery.data!)}
              t={t}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={paymentCustomer !== null}
        onOpenChange={(open) => !open && setPaymentCustomer(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("credits.recordPayment")}</DialogTitle>
          </DialogHeader>
          {paymentCustomer && activeCredit && (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                paymentMutation.mutate();
              }}
            >
              <div className="rounded-md bg-muted p-3 text-sm">
                <p className="font-semibold">{paymentCustomer.customer_name}</p>
                <p className="text-muted-foreground">
                  {t("credits.currentDebt")}:{" "}
                  <strong className="text-foreground">{money(activeCredit.balance)}</strong>
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="credit-payment-amount">{t("credits.amountPaid")}</Label>
                <Input
                  id="credit-payment-amount"
                  type="number"
                  min="1"
                  max={amount(activeCredit.balance)}
                  step="1"
                  required
                  value={paymentAmount}
                  onChange={(event) => setPaymentAmount(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>{t("credits.paymentMethod")}</Label>
                <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {paymentMethods.map((method) => (
                      <SelectItem key={method.value} value={method.value}>
                        {t(method.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="credit-payment-date">{t("credits.date")}</Label>
                <Input
                  id="credit-payment-date"
                  type="date"
                  required
                  value={paymentDate}
                  onChange={(event) => setPaymentDate(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="credit-payment-reference">{t("credits.referenceOptional")}</Label>
                <Input
                  id="credit-payment-reference"
                  value={reference}
                  onChange={(event) => setReference(event.target.value)}
                />
              </div>
              <DialogFooter>
                <Button type="submit" disabled={paymentMutation.isPending}>
                  {paymentMutation.isPending ? t("credits.saving") : t("credits.savePayment")}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof WalletCards;
}) {
  return (
    <div className="panel flex items-center justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="text-muted-foreground text-sm">{label}</p>
        <p className="truncate text-xl font-bold tabular-nums">{value}</p>
      </div>
      <Icon className="text-primary size-5 shrink-0" aria-hidden="true" />
    </div>
  );
}

function CreditDetailPanel({
  detail,
  onPrint,
  onShare,
  t,
}: {
  detail: CreditDetail;
  onPrint: () => void;
  onShare: () => void;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 rounded-md bg-muted p-4 sm:grid-cols-2">
        <p>
          {t("credits.phoneLabel")}: <strong>{detail.customer.phone || "—"}</strong>
        </p>
        <p>
          {t("credits.creditPurchases")}: <strong>{detail.sales_count}</strong>
        </p>
        <p>
          {t("credits.totalCredit")}: <strong>{money(detail.total_credit)}</strong>
        </p>
        <p>
          {t("credits.totalPaid")}: <strong>{money(detail.total_paid)}</strong>
        </p>
        <p className="sm:col-span-2 text-lg">
          {t("credits.totalDebt")}: <strong>{money(detail.balance)}</strong>
        </p>
      </div>

      <div>
        <h3 className="mb-2 font-semibold">{t("credits.creditInvoices")}</h3>
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("credits.date")}</TableHead>
                <TableHead>{t("credits.invoice")}</TableHead>
                <TableHead className="text-right">{t("credits.purchase")}</TableHead>
                <TableHead className="text-right">{t("credits.paid")}</TableHead>
                <TableHead className="text-right">{t("credits.balance")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.sales.map((sale) => (
                <TableRow key={sale.sale_id}>
                  <TableCell>{shortDate(sale.date)}</TableCell>
                  <TableCell>{sale.invoice_number || `Vente #${sale.sale_id}`}</TableCell>
                  <TableCell className="text-right">{money(sale.total_credit)}</TableCell>
                  <TableCell className="text-right">{money(sale.total_paid)}</TableCell>
                  <TableCell className="text-right">{money(sale.balance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div>
        <h3 className="mb-2 font-semibold">{t("credits.paymentHistory")}</h3>
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("credits.date")}</TableHead>
                <TableHead>{t("credits.amount")}</TableHead>
                <TableHead>{t("credits.method")}</TableHead>
                <TableHead>{t("credits.referenceOptional")}</TableHead>
                <TableHead>{t("credits.recordedBy")}</TableHead>
                <TableHead>{t("credits.allocations")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.payments.map((payment) => (
                <TableRow key={payment.id}>
                  <TableCell>{shortDate(payment.payment_date)}</TableCell>
                  <TableCell>{money(payment.amount)}</TableCell>
                  <TableCell>{paymentMethodLabel(payment.payment_method, t)}</TableCell>
                  <TableCell>{payment.reference || `PAY-${payment.id}`}</TableCell>
                  <TableCell>{payment.created_by_name || "—"}</TableCell>
                  <TableCell>
                    {payment.allocations
                      .map(
                        (allocation) =>
                          `${allocation.invoice_number || `Vente #${allocation.sale}`} (${money(allocation.amount)})`,
                      )
                      .join(", ") || "—"}
                  </TableCell>
                </TableRow>
              ))}
              {detail.payments.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">
                    {t("credits.noPayments")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={onPrint}>
          <FileDown className="size-4" /> {t("credits.printStatement")}
        </Button>
        <Button variant="outline" onClick={onShare}>
          <MessageCircle className="size-4" /> WhatsApp
        </Button>
      </div>
    </div>
  );
}
