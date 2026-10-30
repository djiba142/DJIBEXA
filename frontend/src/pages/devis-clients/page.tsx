import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Check, ClipboardList, Plus, Send, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { useAuth } from "@/lib/auth";
import { formatNumber, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/devis-clients")({
  head: () => ({
    meta: [
      { title: "Devis clients — ERP DJIBEXA" },
      { name: "description", content: "Créer des devis et réserver le stock à leur confirmation." },
    ],
  }),
  component: DevisClients,
});

type Customer = { id: number; full_name: string; phone: string; is_active: boolean };
type Location = { id: number; name: string; location_type: string };
type CatalogProduct = {
  id: number;
  name: string;
  sku: string;
  selling_price: string;
  stock_by_location: { location_id: number; quantity: number }[];
};
type OrderItem = {
  id: number;
  product: number;
  product_name: string;
  product_reference: string;
  quantity: number;
  unit_price: string;
  total_price: string;
};
type CustomerOrder = {
  id: number;
  reference: string;
  customer: number;
  customer_name: string;
  location: number;
  location_name: string;
  status: "quote" | "confirmed" | "delivered" | "cancelled";
  discount: string;
  total_amount: string;
  notes: string;
  sale_id: number | null;
  items: OrderItem[];
  created_at: string;
};
type DraftLine = { product: CatalogProduct; quantity: number };

function DevisClients() {
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const { can } = useAuth();
  const canDiscount = can("sales.manage");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [discount, setDiscount] = useState("0");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [search]);

  const ordersQuery = useQuery({
    queryKey: ["customer-orders"],
    queryFn: () => api.list<CustomerOrder>("sales/customer-orders/"),
  });
  const customersQuery = useQuery({
    queryKey: ["customer-order-customers"],
    queryFn: () => api.list<Customer>("customers/"),
  });
  const locationsQuery = useQuery({
    queryKey: ["customer-order-locations"],
    queryFn: () => api.list<Location>("sales/locations/"),
  });
  const productsQuery = useQuery({
    queryKey: ["customer-order-catalog", debouncedSearch],
    enabled: debouncedSearch.length >= 2,
    queryFn: async () => {
      const response = await api.get<{
        results: CatalogProduct[];
      }>("sales/catalog/", { search: debouncedSearch, page_size: 20 });
      return response.results;
    },
  });

  useEffect(() => {
    if (!customerId && customersQuery.data?.length) {
      const activeCustomer = customersQuery.data.find((customer) => customer.is_active);
      if (activeCustomer) setCustomerId(String(activeCustomer.id));
    }
  }, [customerId, customersQuery.data]);
  useEffect(() => {
    if (!locationId && locationsQuery.data?.length) {
      setLocationId(String(locationsQuery.data[0].id));
    }
  }, [locationId, locationsQuery.data]);

  const selectedLocation = locationsQuery.data?.find(
    (location) => String(location.id) === locationId,
  );
  const subtotal = useMemo(
    () => lines.reduce((sum, line) => sum + Number(line.product.selling_price) * line.quantity, 0),
    [lines],
  );
  const discountAmount = canDiscount ? Number(discount || 0) : 0;
  const invalidDiscount =
    !Number.isFinite(discountAmount) || discountAmount < 0 || discountAmount > subtotal;

  const createOrder = useMutation({
    mutationFn: () =>
      api.post<CustomerOrder>("sales/customer-orders/", {
        customer: Number(customerId),
        location: Number(locationId),
        discount: discountAmount.toFixed(2),
        notes,
        items: lines.map(({ product, quantity }) => ({
          product: product.id,
          quantity,
          unit_price: product.selling_price,
        })),
      }),
    onSuccess: (order) => {
      toast.success(t("customerOrders.created"), { description: order.reference });
      setLines([]);
      setDiscount("0");
      setNotes("");
      void queryClient.invalidateQueries({ queryKey: ["customer-orders"] });
    },
    onError: (error: Error) =>
      toast.error(t("customerOrders.createFailed"), { description: error.message }),
  });

  const changeOrder = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "confirm" | "deliver" | "cancel" }) =>
      api.post<CustomerOrder>(`sales/customer-orders/${id}/${action}/`, {}),
    onSuccess: (order) => {
      toast.success(t(`customerOrders.action.${order.status}`));
      void queryClient.invalidateQueries({ queryKey: ["customer-orders"] });
      void queryClient.invalidateQueries({ queryKey: ["sales-catalog"] });
      void queryClient.invalidateQueries({ queryKey: ["sales"] });
      void queryClient.invalidateQueries({ queryKey: ["sales-history"] });
    },
    onError: (error: Error) =>
      toast.error(t("customerOrders.actionFailed"), { description: error.message }),
  });

  function addProduct(product: CatalogProduct) {
    setLines((current) => {
      const existing = current.find((line) => line.product.id === product.id);
      if (existing) {
        return current.map((line) =>
          line.product.id === product.id ? { ...line, quantity: line.quantity + 1 } : line,
        );
      }
      return [...current, { product, quantity: 1 }];
    });
  }

  const customers = (customersQuery.data ?? []).filter((customer) => customer.is_active);
  const orders = ordersQuery.data ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold">{t("customerOrders.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("customerOrders.description")}</p>
      </header>

      <section className="panel space-y-4 p-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Plus className="size-5" />
          {t("customerOrders.newQuote")}
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="quote-customer">{t("customerOrders.customer")}</Label>
            <select
              id="quote-customer"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={customerId}
              onChange={(event) => setCustomerId(event.target.value)}
              disabled={customersQuery.isLoading || customers.length === 0}
            >
              <option value="">{t("customerOrders.chooseCustomer")}</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.full_name}
                  {customer.phone ? ` · ${customer.phone}` : ""}
                </option>
              ))}
            </select>
            {customersQuery.isError && (
              <p className="text-sm text-destructive">{t("customerOrders.customersFailed")}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="quote-location">{t("customerOrders.location")}</Label>
            <select
              id="quote-location"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={locationId}
              onChange={(event) => setLocationId(event.target.value)}
              disabled={locationsQuery.isLoading || !locationsQuery.data?.length}
            >
              <option value="">{t("customerOrders.chooseLocation")}</option>
              {(locationsQuery.data ?? []).map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name}
                </option>
              ))}
            </select>
            {locationsQuery.isError && (
              <p className="text-sm text-destructive">{t("customerOrders.locationsFailed")}</p>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="quote-product-search">{t("customerOrders.searchProducts")}</Label>
          <Input
            id="quote-product-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("customerOrders.searchPlaceholder")}
          />
          {productsQuery.isError && (
            <p className="text-sm text-destructive">{t("customerOrders.catalogFailed")}</p>
          )}
          {debouncedSearch.length >= 2 && (
            <div className="max-h-52 overflow-auto rounded-md border">
              {(productsQuery.data ?? []).map((product) => {
                const stock =
                  product.stock_by_location.find(
                    (item) => item.location_id === selectedLocation?.id,
                  )?.quantity ?? 0;
                return (
                  <div
                    key={product.id}
                    className="flex items-center justify-between gap-3 border-b p-3 last:border-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{product.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {product.sku} · {t("customerOrders.available")}: {formatNumber(stock)} ·{" "}
                        {money(Number(product.selling_price))}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => addProduct(product)}>
                      <Plus /> {t("customerOrders.add")}
                    </Button>
                  </div>
                );
              })}
              {!productsQuery.isLoading && !productsQuery.data?.length && (
                <p className="p-3 text-sm text-muted-foreground">
                  {t("customerOrders.noProducts")}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("customerOrders.product")}</TableHead>
                <TableHead>{t("customerOrders.quantity")}</TableHead>
                <TableHead className="text-right">{t("customerOrders.unitPrice")}</TableHead>
                <TableHead className="text-right">{t("customerOrders.total")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map(({ product, quantity }) => (
                <TableRow key={product.id}>
                  <TableCell>
                    <span className="font-medium">{product.name}</span>
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {product.sku}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Input
                      className="w-24"
                      type="number"
                      min={1}
                      step={1}
                      aria-label={`${t("customerOrders.quantity")} ${product.name}`}
                      value={quantity}
                      onChange={(event) => {
                        const nextQuantity = Math.max(1, Number(event.target.value) || 1);
                        setLines((current) =>
                          current.map((line) =>
                            line.product.id === product.id
                              ? { ...line, quantity: nextQuantity }
                              : line,
                          ),
                        );
                      }}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    {money(Number(product.selling_price))}
                  </TableCell>
                  <TableCell className="text-right">
                    {money(Number(product.selling_price) * quantity)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`${t("customerOrders.remove")} ${product.name}`}
                      onClick={() =>
                        setLines((current) =>
                          current.filter((line) => line.product.id !== product.id),
                        )
                      }
                    >
                      <X />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!lines.length && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    {t("customerOrders.emptyLines")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {canDiscount && (
            <div className="space-y-2">
              <Label htmlFor="quote-discount">{t("customerOrders.discount")}</Label>
              <Input
                id="quote-discount"
                type="number"
                min={0}
                max={subtotal}
                step="any"
                value={discount}
                onChange={(event) => setDiscount(event.target.value)}
              />
            </div>
          )}
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="quote-notes">{t("customerOrders.notes")}</Label>
            <Input
              id="quote-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <p className="text-sm font-semibold">
            {t("customerOrders.estimatedTotal")}: {money(Math.max(0, subtotal - discountAmount))}
          </p>
          <Button
            disabled={
              createOrder.isPending ||
              !customerId ||
              !locationId ||
              !lines.length ||
              invalidDiscount ||
              customersQuery.isError ||
              locationsQuery.isError
            }
            onClick={() => createOrder.mutate()}
          >
            <ClipboardList />
            {createOrder.isPending ? t("customerOrders.saving") : t("customerOrders.saveQuote")}
          </Button>
        </div>
      </section>

      <section className="panel overflow-x-auto p-4">
        <h2 className="mb-4 text-lg font-semibold">{t("customerOrders.history")}</h2>
        {ordersQuery.isError && (
          <p className="mb-3 text-sm text-destructive">{t("customerOrders.loadFailed")}</p>
        )}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("customerOrders.reference")}</TableHead>
              <TableHead>{t("customerOrders.customer")}</TableHead>
              <TableHead>{t("customerOrders.location")}</TableHead>
              <TableHead>{t("customerOrders.items")}</TableHead>
              <TableHead>{t("customerOrders.status")}</TableHead>
              <TableHead className="text-right">{t("customerOrders.total")}</TableHead>
              <TableHead className="text-right">{t("customerOrders.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {orders.map((order) => (
              <TableRow key={order.id}>
                <TableCell className="font-mono text-xs">{order.reference}</TableCell>
                <TableCell>{order.customer_name}</TableCell>
                <TableCell>{order.location_name}</TableCell>
                <TableCell className="min-w-48 text-xs">
                  {order.items.map((item) => (
                    <div key={item.id}>
                      {item.product_name} × {formatNumber(item.quantity)}
                    </div>
                  ))}
                </TableCell>
                <TableCell>{t(`customerOrders.status.${order.status}`)}</TableCell>
                <TableCell className="text-right">{money(Number(order.total_amount))}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    {order.status === "quote" && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          title={t("customerOrders.confirm")}
                          aria-label={`${t("customerOrders.confirm")} ${order.reference}`}
                          disabled={changeOrder.isPending}
                          onClick={() => changeOrder.mutate({ id: order.id, action: "confirm" })}
                        >
                          <Check />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          title={t("customerOrders.cancel")}
                          aria-label={`${t("customerOrders.cancel")} ${order.reference}`}
                          disabled={changeOrder.isPending}
                          onClick={() => changeOrder.mutate({ id: order.id, action: "cancel" })}
                        >
                          <X />
                        </Button>
                      </>
                    )}
                    {order.status === "confirmed" && (
                      <>
                        <Button
                          size="sm"
                          title={t("customerOrders.deliver")}
                          aria-label={`${t("customerOrders.deliver")} ${order.reference}`}
                          disabled={changeOrder.isPending}
                          onClick={() => changeOrder.mutate({ id: order.id, action: "deliver" })}
                        >
                          <Send /> {t("customerOrders.deliver")}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          title={t("customerOrders.cancel")}
                          aria-label={`${t("customerOrders.cancel")} ${order.reference}`}
                          disabled={changeOrder.isPending}
                          onClick={() => changeOrder.mutate({ id: order.id, action: "cancel" })}
                        >
                          <X />
                        </Button>
                      </>
                    )}
                    {order.sale_id !== null && (
                      <span className="self-center text-xs text-muted-foreground">
                        {t("customerOrders.sale")} #{order.sale_id}
                      </span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!orders.length && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  {ordersQuery.isLoading
                    ? t("customerOrders.loading")
                    : t("customerOrders.emptyHistory")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
