import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, Printer, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
import { dateTime, formatNumber, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/ventes/")({
  head: () => ({
    meta: [
      { title: "Ventes — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Historique des ventes du magasin : recherche, filtres par date, vendeur, client et mode de paiement.",
      },
      { property: "og:title", content: "Ventes — DJIBEXA" },
      {
        property: "og:description",
        content: "Historique complet des ventes avec filtres avancés.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Ventes,
});

const PAGE_SIZE = 20;
const ALL = "all";

function Ventes() {
  const { t } = useLocale();
  const [openSale, setOpenSale] = useState<{ id: string; number: string } | null>(null);
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [payment, setPayment] = useState(ALL);
  const [seller, setSeller] = useState(ALL);
  const [customer, setCustomer] = useState(ALL);
  const [page, setPage] = useState(0);

  const reset = () => {
    setSearch("");
    setFrom("");
    setTo("");
    setPayment(ALL);
    setSeller(ALL);
    setCustomer(ALL);
    setPage(0);
  };

  const onFilter =
    <T,>(setter: (v: T) => void) =>
    (value: T) => {
      setter(value);
      setPage(0);
    };

  const { data: customers } = useQuery({
    queryKey: ["customers-list"],
    queryFn: () =>
      api
        .list<{ id: number; full_name: string }>("customers/")
        .then((rows) => rows.map((row) => ({ id: String(row.id), name: row.full_name }))),
  });

  const { data: sales, isFetching } = useQuery({
    queryKey: ["sales"],
    queryFn: () =>
      api.list<{
        id: number;
        invoice_number: string | null;
        total_amount: string;
        payment_method: string;
        created_at: string;
        seller: number | null;
        seller_name: string;
        customer: number | null;
        customer_name: string;
      }>("sales/"),
  });
  const sellers = useMemo(
    () =>
      Array.from(
        new Map(
          (sales ?? [])
            .filter((sale) => sale.seller !== null)
            .map((sale) => [
              String(sale.seller),
              { id: String(sale.seller), full_name: sale.seller_name },
            ]),
        ).values(),
      ),
    [sales],
  );

  const { data: items } = useQuery({
    queryKey: ["sale-items", openSale?.id],
    enabled: !!openSale,
    queryFn: () =>
      api
        .get<{
          items: {
            id: number;
            quantity: number;
            unit_price: string;
            product_name: string;
            stock_origins: {
              source_type: string;
              reference: string;
              quantity: number;
              carton_reference: string | null;
              location: string | null;
              supplier: string | null;
            }[];
            tracked_unit_references: {
              reference: string;
              carton_reference: string;
            }[];
            stock_removed_quantity: number;
          }[];
        }>(`sales/${openSale!.id}/`)
        .then((sale) => sale.items),
  });

  const filteredSales = (sales ?? []).filter((sale) => {
    const saleDate = new Date(sale.created_at);
    const paymentMatches =
      payment === ALL ||
      sale.payment_method ===
        ({ especes: "cash", mobile: "mobile_money", credit: "credit" }[payment] ?? payment);
    return (
      (!search.trim() ||
        (sale.invoice_number ?? String(sale.id)).toLowerCase().includes(search.toLowerCase())) &&
      (!from || saleDate >= new Date(`${from}T00:00:00`)) &&
      (!to || saleDate <= new Date(`${to}T23:59:59.999`)) &&
      paymentMatches &&
      (seller === ALL || String(sale.seller ?? "") === seller) &&
      (customer === ALL || String(sale.customer ?? "") === customer)
    );
  });
  const total = filteredSales.length;
  const rows = filteredSales.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const sellerName = (id: string) =>
    (sellers ?? []).find((s) => s.id === id)?.full_name || t("sales.history.seller");
  const hasFilters =
    !!search || !!from || !!to || payment !== ALL || seller !== ALL || customer !== ALL;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("sales.history.title")}</h1>
          <p className="text-muted-foreground text-sm">
            {t("sales.history.count", {
              count: formatNumber(total),
              state: t(hasFilters ? "sales.history.found" : "sales.history.recorded"),
            })}
          </p>
        </div>
      </div>

      <div className="panel grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
        <Input
          placeholder={t("sales.history.search")}
          value={search}
          onChange={(e) => onFilter(setSearch)(e.target.value)}
        />
        <div className="flex gap-2">
          <Input type="date" value={from} onChange={(e) => onFilter(setFrom)(e.target.value)} />
          <Input type="date" value={to} onChange={(e) => onFilter(setTo)(e.target.value)} />
        </div>
        <Select value={payment} onValueChange={onFilter(setPayment)}>
          <SelectTrigger>
            <SelectValue placeholder={t("sales.history.payment")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("sales.history.allPayments")}</SelectItem>
            <SelectItem value="especes">{t("sales.cash")}</SelectItem>
            <SelectItem value="mobile">{t("sales.mobileMoney")}</SelectItem>
            <SelectItem value="credit">{t("sales.credit")}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={seller} onValueChange={onFilter(setSeller)}>
          <SelectTrigger>
            <SelectValue placeholder={t("sales.history.seller")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("sales.history.allSellers")}</SelectItem>
            {(sellers ?? []).map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.full_name || "—"}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={customer} onValueChange={onFilter(setCustomer)}>
          <SelectTrigger>
            <SelectValue placeholder={t("sales.history.client")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("sales.history.allCustomers")}</SelectItem>
            {(customers ?? []).map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={reset} disabled={!hasFilters}>
          <X className="size-4" /> {t("sales.history.reset")}
        </Button>
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("sales.history.ticket")}</TableHead>
              <TableHead>{t("sales.history.client")}</TableHead>
              <TableHead className="hidden lg:table-cell">{t("sales.history.seller")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("sales.history.payment")}</TableHead>
              <TableHead className="hidden md:table-cell">{t("sales.history.date")}</TableHead>
              <TableHead className="text-right">{t("sales.total")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((s) => (
              <TableRow
                key={s.id}
                className="cursor-pointer"
                onClick={() =>
                  setOpenSale({ id: String(s.id), number: s.invoice_number ?? `VTE-${s.id}` })
                }
              >
                <TableCell className="font-mono text-xs">
                  {s.invoice_number ?? `VTE-${s.id}`}
                </TableCell>
                <TableCell>{s.customer_name || t("sales.customerCounter")}</TableCell>
                <TableCell className="hidden lg:table-cell">
                  {s.seller_name || sellerName(String(s.seller ?? ""))}
                </TableCell>
                <TableCell className="hidden capitalize sm:table-cell">
                  {{
                    cash: t("sales.cash"),
                    mobile_money: t("sales.mobileMoney"),
                    bank_transfer: t("sales.payment.bankTransfer"),
                    credit: t("sales.credit"),
                  }[s.payment_method] ?? s.payment_method}
                </TableCell>
                <TableCell className="text-muted-foreground hidden text-xs md:table-cell">
                  {dateTime(s.created_at)}
                </TableCell>
                <TableCell className="text-right font-semibold">
                  {money(Number(s.total_amount))}
                </TableCell>
              </TableRow>
            ))}
            {!rows.length && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground py-10 text-center">
                  {isFetching ? t("reports.loading") : t("sales.history.noMatch")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-muted-foreground text-sm">
            {t("products.page", { current: String(page + 1), total: String(lastPage + 1) })}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="size-4" /> {t("common.previous")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= lastPage}
              onClick={() => setPage((p) => p + 1)}
            >
              {t("common.next")} <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}

      <Dialog open={!!openSale} onOpenChange={(o) => !o && setOpenSale(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {t("sales.history.invoice")} {openSale?.number}
            </DialogTitle>
          </DialogHeader>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("inventory.product")}</TableHead>
                <TableHead>{t("sales.history.origin")}</TableHead>
                <TableHead className="text-right">{t("sales.unit")}</TableHead>
                <TableHead className="text-right">{t("sales.history.removedStock")}</TableHead>
                <TableHead className="text-right">{t("sales.total")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(items ?? []).map((it) => (
                <TableRow key={it.id}>
                  <TableCell>{it.product_name ?? "—"}</TableCell>
                  <TableCell className="max-w-md text-xs">
                    <div className="space-y-1">
                      {it.stock_origins.map((origin, index) => (
                        <p key={`${origin.source_type}-${origin.reference}-${index}`}>
                          <span className="font-medium">
                            {origin.source_type === "carton"
                              ? t("sales.history.origin.carton")
                              : origin.source_type === "external_supplier"
                                ? t("sales.history.origin.external")
                                : t("sales.history.origin.unknown")}
                          </span>
                          {": "}
                          {origin.carton_reference ?? origin.reference}
                          {" × "}
                          {origin.quantity}
                          {origin.location ? ` · ${origin.location}` : ""}
                          {origin.supplier ? ` · ${origin.supplier}` : ""}
                        </p>
                      ))}
                      {it.tracked_unit_references.length > 0 && (
                        <p className="text-muted-foreground break-words">
                          {t("sales.history.origin.pieces")}:{" "}
                          {it.tracked_unit_references.map((unit) => unit.reference).join(", ")}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">{it.quantity}</TableCell>
                  <TableCell className="text-right">{it.stock_removed_quantity}</TableCell>
                  <TableCell className="text-right font-medium">
                    {money(it.quantity * Number(it.unit_price))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {openSale && (
            <Button asChild className="w-full">
              <Link to="/ventes/$saleId" params={{ saleId: openSale.id }}>
                <Printer className="size-4" /> {t("sales.history.printableInvoice")}
              </Link>
            </Button>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
