import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Minus, Plus, ShoppingBasket, SlidersHorizontal, Trash2, Truck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatNumber, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/ventes/nouvelle")({
  head: () => ({
    meta: [
      { title: "Nouvelle vente — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Caisse rapide : recherche de pièces, panier, remise et encaissement en quelques clics.",
      },
      { property: "og:title", content: "Nouvelle vente — DJIBEXA" },
      { property: "og:description", content: "Interface de caisse du magasin." },
    ],
  }),
  component: NouvelleVente,
});

type Line = {
  id: string;
  productId: string | null;
  name: string;
  reference: string;
  price: number;
  qty: number;
  stock: number;
  manual: boolean;
  externalPurchase: ExternalPurchaseDraft | null;
};
type ExternalPurchaseDraft = {
  supplierId: string;
  unitCost: string;
  additionalCost: string;
  paymentTerms: "immediate" | "deferred";
  dueDate: string;
  deliveryMode: "direct" | "warehouse";
  proofReference: string;
  notes: string;
};
type SupplierOption = { id: number; name: string };
type SaleCatalogProduct = {
  id: string;
  name: string;
  reference: string;
  alternative_references: string;
  category_id: number | null;
  brand: string;
  vehicle: string;
  sale_price: number;
  stock_by_location: { location_id: number; location: string; quantity: number }[];
};
function localDateString() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

function NouvelleVente() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { t } = useLocale();
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [availabilityFilter, setAvailabilityFilter] = useState("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [catalogPage, setCatalogPage] = useState(1);
  const [lines, setLines] = useState<Line[]>([]);
  const [customerId, setCustomerId] = useState("comptoir");
  const [payment, setPayment] = useState("especes");
  const [discount, setDiscount] = useState("0");
  const [locationId, setLocationId] = useState("");
  const [step, setStep] = useState<"items" | "confirm">("items");
  const checkoutRequest = useRef<{ fingerprint: string; key: string } | null>(null);
  const hasExternalPurchaseLines = lines.some((line) => line.externalPurchase !== null);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [search]);

  const {
    data: products,
    isLoading: productsLoading,
    isError: productsError,
    refetch: refetchProducts,
  } = useQuery({
    queryKey: ["sales-catalog", debouncedSearch, categoryFilter, availabilityFilter, catalogPage],
    enabled: debouncedSearch.length >= 2,
    queryFn: async () => {
      const response = await api.get<{
        count: number;
        next: string | null;
        previous: string | null;
        results: {
          id: number;
          name: string;
          sku: string;
          alternative_references: string;
          category: number | null;
          brand: string;
          vehicle: string;
          selling_price: string;
          quantity: number;
          stock_by_location: SaleCatalogProduct["stock_by_location"];
        }[];
      }>("sales/catalog/", {
        search: debouncedSearch,
        page: catalogPage,
        page_size: 20,
        ...(categoryFilter === "all" ? {} : { category: categoryFilter }),
        ...(availabilityFilter === "all" ? {} : { available: availabilityFilter === "available" }),
      });
      return {
        count: response.count,
        next: response.next,
        previous: response.previous,
        results: response.results.map((product) => ({
          id: String(product.id),
          name: product.name,
          reference: product.sku,
          alternative_references: product.alternative_references,
          category_id: product.category,
          brand: product.brand,
          vehicle: product.vehicle,
          sale_price: Number(product.selling_price),
          stock_by_location: product.stock_by_location,
        })),
      };
    },
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => api.list<{ id: number; name: string }>("products/categories/"),
    enabled: filtersOpen,
  });

  const { data: customers } = useQuery({
    queryKey: ["customers"],
    queryFn: async () =>
      (await api.list<{ id: number; full_name: string; phone: string }>("customers/"))
        .filter((customer) => customer.full_name !== "Client comptoir" || customer.phone)
        .map((customer) => ({
          id: String(customer.id),
          name: customer.full_name,
          phone: customer.phone,
        })),
  });
  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: () => api.list<SupplierOption>("sales/external-suppliers/"),
    enabled: hasExternalPurchaseLines,
  });

  const {
    data: locations,
    isLoading: locationsLoading,
    isError: locationsError,
    refetch: refetchLocations,
  } = useQuery({
    queryKey: ["stock-location-options"],
    queryFn: () =>
      api.list<{ id: number; name: string; location_type: string }>("sales/locations/"),
  });
  const saleLocation =
    locations?.find((location) => String(location.id) === locationId) ?? locations?.[0];

  const stockAtSaleLocation = useCallback(
    (product: SaleCatalogProduct): number => {
      if (!saleLocation) return 0;
      return (
        product.stock_by_location.find((stock) => stock.location_id === saleLocation.id)
          ?.quantity ?? 0
      );
    },
    [saleLocation],
  );

  const results = useMemo(() => {
    return (products?.results ?? []).map((product) => ({
      ...product,
      stock: stockAtSaleLocation(product),
    }));
  }, [products, stockAtSaleLocation]);

  const requestReplenishment = useMutation({
    mutationFn: async ({
      productId,
      shopId,
      quantity,
    }: {
      productId: string;
      shopId: number;
      quantity: number;
    }) =>
      api.post("inventory/replenishment-requests/", {
        product: Number(productId),
        shop: shopId,
        requested_quantity: quantity,
        request_reason: "Rupture signalée lors d'une vente.",
      }),
    onSuccess: () => {
      toast.success(t("sales.replenishmentRequested"));
      void qc.invalidateQueries({ queryKey: ["notifications"] });
      void qc.invalidateQueries({ queryKey: ["supply_requests"] });
    },
    onError: (error: Error) =>
      toast.error(t("sales.replenishmentError"), { description: error.message }),
  });

  const subtotal = lines.reduce((s, l) => s + l.price * l.qty, 0);
  const cartQuantity = lines.reduce((quantity, line) => quantity + line.qty, 0);
  const discountAmount = Number(discount || 0);
  const discountIsInvalid =
    !Number.isFinite(discountAmount) || discountAmount < 0 || discountAmount > subtotal;
  const selectedCustomer = customers?.find((customer) => customer.id === customerId);
  const creditNeedsCustomer = payment === "credit" && customerId === "comptoir";
  const creditCustomerMissingPhone =
    payment === "credit" && customerId !== "comptoir" && !selectedCustomer?.phone.trim();
  const total = Math.max(0, subtotal - discountAmount);

  function addLine(
    p: { id: string; name: string; reference?: string; sale_price: number; stock: number },
    quantity = 1,
    external = false,
  ): boolean {
    if (!external && p.stock <= 0) {
      toast.error(t("sales.outOfStockTitle"), {
        description: t("sales.outOfStockDescription"),
      });
      return false;
    }

    const lineId = `${external ? "external" : "product"}-${p.id}`;
    const currentQuantity = lines.find((line) => line.id === lineId)?.qty ?? 0;
    if (!external && currentQuantity + quantity > p.stock) {
      toast.error(t("sales.insufficientStock"), {
        description: t("sales.stockAvailable", {
          available: p.stock,
          inCart: currentQuantity,
          requested: quantity,
        }),
      });
      return false;
    }
    setLines((prev) => {
      const found = prev.find((line) => line.id === lineId);
      if (found)
        return prev.map((l) =>
          l.id === lineId
            ? { ...l, qty: external ? l.qty + quantity : Math.min(l.stock, l.qty + quantity) }
            : l,
        );
      return [
        ...prev,
        {
          id: lineId,
          productId: p.id,
          name: p.name,
          reference: p.reference ?? "",
          price: p.sale_price,
          qty: quantity,
          stock: p.stock,
          manual: false,
          externalPurchase: external
            ? {
                supplierId: "",
                unitCost: "",
                additionalCost: "0",
                paymentTerms: "immediate",
                dueDate: "",
                deliveryMode: "direct",
                proofReference: "",
                notes: "",
              }
            : null,
        },
      ];
    });
    setSearch("");
    return true;
  }

  function requestProductReplenishment(productId: string) {
    if (!saleLocation) return;
    const entered = window.prompt(t("sales.replenishmentQuantity"), "1");
    if (entered === null) return;
    const quantity = Number(entered);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      toast.error(t("sales.replenishmentError"), {
        description: t("sales.replenishmentQuantity"),
      });
      return;
    }
    requestReplenishment.mutate({
      productId,
      shopId: saleLocation.id,
      quantity,
    });
  }

  function setQty(id: string, qty: number) {
    setLines((prev) =>
      prev.map((line) =>
        line.id === id
          ? {
              ...line,
              qty: Math.max(
                1,
                line.externalPurchase || line.manual ? qty : Math.min(line.stock, qty),
              ),
            }
          : line,
      ),
    );
  }

  function addManualLine(description = "") {
    setLines((current) => [
      ...current,
      {
        id: `manual-${crypto.randomUUID()}`,
        productId: null,
        name: description,
        reference: "",
        price: 0,
        qty: 1,
        stock: 0,
        manual: true,
        externalPurchase: null,
      },
    ]);
    setSearch("");
  }

  function updateLine(id: string, patch: Partial<Line>) {
    setLines((current) => current.map((line) => (line.id === id ? { ...line, ...patch } : line)));
  }

  function toggleExternalPurchase(line: Line, enabled: boolean) {
    updateLine(line.id, {
      externalPurchase: enabled
        ? {
            supplierId: "",
            unitCost: "",
            additionalCost: "0",
            paymentTerms: "immediate",
            dueDate: "",
            deliveryMode: "direct",
            proofReference: "",
            notes: "",
          }
        : null,
    });
  }

  const missingLines = lines.filter(
    (line) => line.productId && !line.externalPurchase && line.qty > line.stock,
  );
  const invalidLines = lines.filter(
    (line) =>
      !line.name.trim() ||
      !Number.isFinite(line.price) ||
      line.price <= 0 ||
      !Number.isInteger(line.qty) ||
      line.qty <= 0 ||
      (line.externalPurchase &&
        (!line.externalPurchase.supplierId ||
          line.externalPurchase.unitCost === "" ||
          !Number.isFinite(Number(line.externalPurchase.unitCost)) ||
          Number(line.externalPurchase.unitCost) < 0 ||
          !Number.isFinite(Number(line.externalPurchase.additionalCost)) ||
          Number(line.externalPurchase.additionalCost) < 0 ||
          (line.externalPurchase.paymentTerms === "deferred" && !line.externalPurchase.dueDate))),
  );

  const checkout = useMutation({
    mutationFn: async () => {
      if (missingLines.length || invalidLines.length) {
        throw new Error(
          missingLines.length ? t("sales.stockCoverageError") : t("sales.completeLineDetails"),
        );
      }
      const payload = {
        customer: customerId === "comptoir" ? null : Number(customerId),
        location: saleLocation?.id ?? null,
        payment_method: payment === "especes" ? "cash" : payment,
        status: payment === "credit" ? "partial" : "paid",
        amount_paid: payment === "credit" ? 0 : total,
        discount: Number(discount || 0),
        items: lines.map((line) => ({
          product: line.productId ? Number(line.productId) : null,
          ...(!line.productId
            ? { item_name: line.name.trim(), item_reference: line.reference.trim() }
            : {}),
          quantity: line.qty,
          unit_price: line.price,
          ...(line.externalPurchase
            ? {
                external_purchase: {
                  supplier: Number(line.externalPurchase.supplierId),
                  unit_cost: Number(line.externalPurchase.unitCost).toFixed(2),
                  additional_cost: Number(line.externalPurchase.additionalCost || 0).toFixed(2),
                  payment_terms: line.externalPurchase.paymentTerms,
                  due_date:
                    line.externalPurchase.paymentTerms === "immediate"
                      ? localDateString()
                      : line.externalPurchase.dueDate,
                  delivery_mode: line.externalPurchase.deliveryMode,
                  proof_reference: line.externalPurchase.proofReference.trim(),
                  notes: line.externalPurchase.notes.trim(),
                },
              }
            : {}),
        })),
      };
      const fingerprint = JSON.stringify(payload);
      const request =
        checkoutRequest.current?.fingerprint === fingerprint
          ? checkoutRequest.current
          : { fingerprint, key: crypto.randomUUID() };
      checkoutRequest.current = request;
      const sale = await api.post<{ id: number; invoice_number: string | null }>(
        "sales/",
        payload,
        { "Idempotency-Key": request.key },
      );
      return { id: String(sale.id), number: sale.invoice_number ?? `VTE-${sale.id}` };
    },
    onSuccess: (sale) => {
      checkoutRequest.current = null;
      toast.success(t("sales.saleRecorded", { number: sale.number }), {
        description: money(total),
      });
      setLines([]);
      setDiscount("0");
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["sales"] });
      void qc.invalidateQueries({ queryKey: ["external-purchases"] });
      void qc.invalidateQueries({ queryKey: ["external-purchase-summary"] });
      void qc.invalidateQueries({ queryKey: ["external-purchase-payments"] });
      void navigate({ to: "/ventes/$saleId", params: { saleId: sale.id } });
    },
    onError: (e: Error) => toast.error(t("sales.saleImpossible"), { description: e.message }),
  });

  return (
    <div className="space-y-4 pb-24 lg:space-y-5 lg:pb-0">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold sm:text-3xl">{t("sales.new")}</h1>
        <p className="text-muted-foreground text-sm">
          {t("sales.shopLabel")}:{" "}
          <span className="font-medium text-foreground">
            {saleLocation?.name ??
              (locationsLoading
                ? t("sales.locationLoading")
                : locationsError
                  ? t("sales.locationLoadFailed")
                  : t("sales.locationMissing"))}
          </span>
        </p>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2" aria-label={t("sales.stepsLabel")}>
        {(["items", "confirm"] as const).map((currentStep, index) => (
          <li
            key={currentStep}
            aria-current={step === currentStep ? "step" : undefined}
            className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold ${
              step === currentStep ? "border-primary bg-primary/5" : "text-muted-foreground"
            }`}
          >
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full border text-xs">
              {index + 1}
            </span>
            {index + 1}. {t(currentStep === "items" ? "sales.stepItems" : "sales.stepConfirm")}
          </li>
        ))}
      </ol>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          {step === "items" && (
            <div className="panel relative space-y-4 p-3 sm:p-4">
              {locationsError ? (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span className="text-destructive">{t("sales.locationLoadFailed")}</span>
                  <Button variant="outline" size="sm" onClick={() => void refetchLocations()}>
                    {t("common.retry")}
                  </Button>
                </div>
              ) : locationsLoading ? (
                <p className="text-muted-foreground text-sm">{t("sales.locationLoading")}</p>
              ) : !saleLocation ? (
                <p role="alert" className="text-destructive text-sm">
                  {t("sales.locationMissing")}
                </p>
              ) : null}
              {(locations?.length ?? 0) > 1 && (
                <div className="space-y-1.5">
                  <Label htmlFor="sale-location">{t("sales.saleLocation")}</Label>
                  <Select
                    value={String(saleLocation?.id ?? "")}
                    onValueChange={setLocationId}
                    disabled={lines.length > 0}
                  >
                    <SelectTrigger id="sale-location" className="h-12">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {locations?.map((location) => (
                        <SelectItem key={location.id} value={String(location.id)}>
                          {location.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="space-y-2">
                <div className="min-w-0 flex-1 space-y-1.5">
                  <Label htmlFor="sale-product-search">{t("sales.searchPart")}</Label>
                  <Input
                    id="sale-product-search"
                    autoFocus
                    className="h-14 text-base"
                    placeholder={t("sales.referencePlaceholder")}
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setCatalogPage(1);
                    }}
                  />
                </div>
                <Link
                  to="/recherche"
                  search={{ q: search.trim() }}
                  className="text-primary text-sm hover:underline"
                >
                  {t("search.title")}
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  className="h-11 w-full justify-start"
                  onClick={addManualLine}
                >
                  <Plus className="mr-2 size-4" />
                  {t("sales.addOneOffItem")}
                </Button>
              </div>
              <Button
                type="button"
                variant="outline"
                className="h-12 w-full justify-start"
                aria-expanded={filtersOpen}
                onClick={() => setFiltersOpen((open) => !open)}
              >
                <SlidersHorizontal />
                {t("sales.filterAction")}
              </Button>
              {filtersOpen && (
                <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>{t("sales.filterCategory")}</Label>
                    <Select
                      value={categoryFilter}
                      onValueChange={(value) => {
                        setCategoryFilter(value);
                        setCatalogPage(1);
                      }}
                    >
                      <SelectTrigger aria-label={t("sales.filterCategory")} className="h-12">
                        <SelectValue placeholder={t("sales.filterCategory")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">{t("sales.allCategories")}</SelectItem>
                        {(categories ?? []).map((category) => (
                          <SelectItem key={category.id} value={String(category.id)}>
                            {category.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>{t("sales.filterAvailability")}</Label>
                    <Select
                      value={availabilityFilter}
                      onValueChange={(value) => {
                        setAvailabilityFilter(value);
                        setCatalogPage(1);
                      }}
                    >
                      <SelectTrigger aria-label={t("sales.filterAvailability")} className="h-12">
                        <SelectValue placeholder={t("sales.filterAvailability")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">{t("sales.allAvailability")}</SelectItem>
                        <SelectItem value="available">{t("sales.availableOnly")}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
              {search.trim().length === 1 && (
                <p className="text-muted-foreground text-sm">{t("sales.searchMinChars")}</p>
              )}
              {productsLoading && (
                <p className="text-muted-foreground text-sm">{t("sales.catalogLoading")}</p>
              )}
              {productsError && (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span className="text-destructive">{t("sales.catalogFailed")}</span>
                  <Button variant="outline" size="sm" onClick={() => void refetchProducts()}>
                    {t("common.retry")}
                  </Button>
                </div>
              )}
              {results.length > 0 && (
                <div className="space-y-2">
                  {results.map((p) => (
                    <div key={p.id} className="space-y-3 rounded-md border p-3">
                      <div className="min-w-0">
                        <p className="font-semibold">{p.name}</p>
                        <p className="text-muted-foreground mt-1 font-mono text-sm">
                          {t("sales.referenceLabel")}: {p.reference}
                        </p>
                        {(p.brand || p.vehicle) && (
                          <p className="text-muted-foreground mt-1 text-sm">
                            {[p.brand, p.vehicle].filter(Boolean).join(" · ")}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold">{money(p.sale_price)}</span>
                        {p.stock > 0 ? (
                          <span className="text-muted-foreground text-sm">
                            {t("sales.stockAtLocation", {
                              quantity: p.stock,
                              location: saleLocation?.name ?? "",
                            })}
                          </span>
                        ) : (
                          <span className="text-destructive text-sm font-medium">
                            {t("sales.outOfStock")}
                          </span>
                        )}
                      </div>
                      <Button
                        type="button"
                        className="h-12 w-full"
                        disabled={p.stock <= 0 || !saleLocation}
                        onClick={() => addLine(p)}
                      >
                        <ShoppingBasket />
                        {t("sales.addProduct")}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-11 w-full"
                        disabled={!saleLocation}
                        onClick={() => addLine(p, 1, true)}
                      >
                        <Truck className="mr-2 size-4" />
                        {t("sales.addWithExternalPurchase")}
                      </Button>
                      {p.stock <= 0 && (
                        <Button
                          type="button"
                          variant="outline"
                          className="w-full"
                          disabled={!saleLocation || requestReplenishment.isPending}
                          onClick={() => requestProductReplenishment(p.id)}
                        >
                          {t("sales.requestReplenishment")}
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {search.trim().length >= 2 &&
                !results.length &&
                !productsLoading &&
                !productsError && (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
                    <p className="text-muted-foreground min-w-0 flex-1 text-sm">
                      {t("sales.noPartsFound")}
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => addManualLine(search.trim())}
                    >
                      {t("sales.addOneOffItem")}
                    </Button>
                  </div>
                )}
              {!search.trim() && (
                <p className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
                  {t("sales.catalogPrompt")}
                </p>
              )}
              {search.trim().length >= 2 && products && products.count > 0 && (
                <div className="flex items-center justify-between gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!products.previous || productsLoading}
                    onClick={() => setCatalogPage((current) => Math.max(1, current - 1))}
                  >
                    {t("sales.previousPage")}
                  </Button>
                  <span className="text-muted-foreground text-xs">
                    {t("sales.catalogPage", {
                      page: catalogPage,
                      pages: Math.ceil(products.count / 20),
                      count: products.count,
                    })}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!products.next || productsLoading}
                    onClick={() => setCatalogPage((current) => current + 1)}
                  >
                    {t("sales.nextPage")}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="panel h-fit space-y-4 p-3 sm:p-4 lg:sticky lg:top-4">
          <div className="flex items-center justify-between gap-3 border-b pb-3">
            <h2 className="text-lg font-semibold">{t("sales.cartTitle")}</h2>
            <span className="text-muted-foreground text-sm">
              {t(cartQuantity === 1 ? "sales.cartCountOne" : "sales.cartCountMany", {
                count: formatNumber(cartQuantity),
              })}
            </span>
          </div>
          <div
            className={`divide-y overflow-y-auto ${
              hasExternalPurchaseLines || lines.some((line) => line.manual) ? "" : "max-h-[42vh]"
            }`}
          >
            {lines.map((l) => (
              <div key={l.id} className="flex flex-wrap items-center gap-2 py-3">
                <div className="min-w-0 flex-1">
                  {l.manual && step === "items" ? (
                    <Input
                      aria-label={t("sales.itemName")}
                      placeholder={t("sales.itemName")}
                      value={l.name}
                      onChange={(event) => updateLine(l.id, { name: event.target.value })}
                      maxLength={220}
                    />
                  ) : (
                    <p className="truncate font-medium">{l.name}</p>
                  )}
                  {l.manual && step === "items" && (
                    <Input
                      className="mt-2"
                      aria-label={t("sales.itemReference")}
                      placeholder={t("sales.itemReference")}
                      value={l.reference}
                      onChange={(event) => updateLine(l.id, { reference: event.target.value })}
                      maxLength={120}
                    />
                  )}
                  <p className="text-muted-foreground text-sm">
                    {l.reference && (!l.manual || step !== "items") && (
                      <>
                        <span className="font-mono">{l.reference}</span>
                        <span> · </span>
                      </>
                    )}
                    {t("sales.unitPrice", { price: money(l.price) })}
                  </p>
                  {l.manual && step === "items" && (
                    <div className="mt-2 flex items-center gap-2">
                      <Label htmlFor={`one-off-price-${l.id}`}>{t("sales.saleUnitPrice")}</Label>
                      <Input
                        id={`one-off-price-${l.id}`}
                        type="number"
                        min="0.01"
                        step="0.01"
                        className="h-10 w-36"
                        value={l.price || ""}
                        onChange={(event) =>
                          updateLine(l.id, { price: Number(event.target.value) || 0 })
                        }
                      />
                    </div>
                  )}
                  {l.productId && !l.externalPurchase && l.qty > l.stock && (
                    <p className="text-destructive mt-1 text-xs font-medium">
                      {l.stock > 0
                        ? t("sales.partialStock", {
                            available: l.stock,
                            backorder: l.qty - l.stock,
                          })
                        : t("sales.backorder", { quantity: l.qty })}
                    </p>
                  )}
                </div>
                {step === "items" ? (
                  <div className="flex items-center gap-2">
                    <Button
                      size="icon"
                      variant="outline"
                      className="size-12"
                      aria-label={`${t("sales.decreaseQuantity")}: ${l.name}`}
                      disabled={l.qty <= 1}
                      onClick={() => setQty(l.id, l.qty - 1)}
                    >
                      <Minus className="size-4" />
                    </Button>
                    <Input
                      className="h-12 w-14 text-center"
                      aria-label={`${t("sales.quantity")}: ${l.name}`}
                      value={l.qty}
                      onChange={(e) => setQty(l.id, Number(e.target.value) || 1)}
                    />
                    <Button
                      size="icon"
                      variant="outline"
                      className="size-12"
                      aria-label={`${t("sales.increaseQuantity")}: ${l.name}`}
                      disabled={!l.externalPurchase && !l.manual && l.qty >= l.stock}
                      onClick={() => setQty(l.id, l.qty + 1)}
                    >
                      <Plus className="size-4" />
                    </Button>
                  </div>
                ) : (
                  <p className="min-w-20 text-center text-base">
                    {t("sales.quantity")}: <strong>{l.qty}</strong>
                  </p>
                )}
                {step === "items" && (
                  <div className="w-full space-y-3 rounded-md bg-muted/40 p-3">
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`external-purchase-${l.id}`}
                        checked={l.externalPurchase !== null}
                        onCheckedChange={(checked) => toggleExternalPurchase(l, checked === true)}
                      />
                      <Label htmlFor={`external-purchase-${l.id}`}>
                        {t("sales.needsExternalPurchase")}
                      </Label>
                    </div>
                    {l.externalPurchase && (
                      <>
                        {suppliersQuery.isError ? (
                          <p role="alert" className="text-destructive text-sm">
                            {t("sales.suppliersLoadFailed")}
                          </p>
                        ) : null}
                        <div className="grid gap-3 sm:grid-cols-2">
                          <div className="space-y-1.5">
                            <Label htmlFor={`supplier-${l.id}`}>
                              {t("sales.externalSupplier")}
                            </Label>
                            <Select
                              value={l.externalPurchase.supplierId}
                              onValueChange={(supplierId) =>
                                updateLine(l.id, {
                                  externalPurchase: { ...l.externalPurchase!, supplierId },
                                })
                              }
                              disabled={suppliersQuery.isLoading || suppliersQuery.isError}
                            >
                              <SelectTrigger id={`supplier-${l.id}`}>
                                <SelectValue placeholder={t("sales.chooseSupplier")} />
                              </SelectTrigger>
                              <SelectContent>
                                {(suppliersQuery.data ?? []).map((supplier) => (
                                  <SelectItem key={supplier.id} value={String(supplier.id)}>
                                    {supplier.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor={`unit-cost-${l.id}`}>
                              {t("sales.purchaseUnitCost")}
                            </Label>
                            <Input
                              id={`unit-cost-${l.id}`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={l.externalPurchase.unitCost}
                              onChange={(event) =>
                                updateLine(l.id, {
                                  externalPurchase: {
                                    ...l.externalPurchase!,
                                    unitCost: event.target.value,
                                  },
                                })
                              }
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor={`additional-cost-${l.id}`}>
                              {t("sales.additionalPurchaseCost")}
                            </Label>
                            <Input
                              id={`additional-cost-${l.id}`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={l.externalPurchase.additionalCost}
                              onChange={(event) =>
                                updateLine(l.id, {
                                  externalPurchase: {
                                    ...l.externalPurchase!,
                                    additionalCost: event.target.value,
                                  },
                                })
                              }
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor={`payment-terms-${l.id}`}>
                              {t("sales.supplierPaymentTerms")}
                            </Label>
                            <Select
                              value={l.externalPurchase.paymentTerms}
                              onValueChange={(paymentTerms: "immediate" | "deferred") =>
                                updateLine(l.id, {
                                  externalPurchase: {
                                    ...l.externalPurchase!,
                                    paymentTerms,
                                  },
                                })
                              }
                            >
                              <SelectTrigger id={`payment-terms-${l.id}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="immediate">
                                  {t("sales.paymentImmediate")}
                                </SelectItem>
                                <SelectItem value="deferred">
                                  {t("sales.paymentDeferred")}
                                </SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          {l.externalPurchase.paymentTerms === "deferred" && (
                            <div className="space-y-1.5">
                              <Label htmlFor={`due-date-${l.id}`}>
                                {t("sales.supplierDueDate")}
                              </Label>
                              <Input
                                id={`due-date-${l.id}`}
                                type="date"
                                value={l.externalPurchase.dueDate}
                                onChange={(event) =>
                                  updateLine(l.id, {
                                    externalPurchase: {
                                      ...l.externalPurchase!,
                                      dueDate: event.target.value,
                                    },
                                  })
                                }
                              />
                            </div>
                          )}
                          <div className="space-y-1.5">
                            <Label htmlFor={`delivery-mode-${l.id}`}>
                              {t("sales.externalDeliveryMode")}
                            </Label>
                            <Select
                              value={l.externalPurchase.deliveryMode}
                              onValueChange={(deliveryMode: "direct" | "warehouse") =>
                                updateLine(l.id, {
                                  externalPurchase: {
                                    ...l.externalPurchase!,
                                    deliveryMode,
                                  },
                                })
                              }
                            >
                              <SelectTrigger id={`delivery-mode-${l.id}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="direct">
                                  {t("externalPurchases.direct")}
                                </SelectItem>
                                <SelectItem value="warehouse">
                                  {t("externalPurchases.warehouse")}
                                </SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-1.5 sm:col-span-2">
                            <Label htmlFor={`proof-reference-${l.id}`}>
                              {t("sales.purchaseProofReference")}
                            </Label>
                            <Input
                              id={`proof-reference-${l.id}`}
                              value={l.externalPurchase.proofReference}
                              onChange={(event) =>
                                updateLine(l.id, {
                                  externalPurchase: {
                                    ...l.externalPurchase!,
                                    proofReference: event.target.value,
                                  },
                                })
                              }
                            />
                          </div>
                          <div className="space-y-1.5 sm:col-span-2">
                            <Label htmlFor={`purchase-notes-${l.id}`}>
                              {t("sales.purchaseNotes")}
                            </Label>
                            <Input
                              id={`purchase-notes-${l.id}`}
                              value={l.externalPurchase.notes}
                              onChange={(event) =>
                                updateLine(l.id, {
                                  externalPurchase: {
                                    ...l.externalPurchase!,
                                    notes: event.target.value,
                                  },
                                })
                              }
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
                <p className="w-full text-right font-semibold sm:w-24">
                  {t("sales.lineSubtotal", { total: money(l.price * l.qty) })}
                </p>
                {step === "items" && (
                  <Button
                    variant="outline"
                    className="h-12"
                    aria-label={`${t("sales.removeProduct")}: ${l.name}`}
                    onClick={() => {
                      setLines((previous) => previous.filter((line) => line.id !== l.id));
                    }}
                  >
                    <Trash2 className="size-4" />
                    <span>{t("sales.removeShort")}</span>
                  </Button>
                )}
              </div>
            ))}
            {!lines.length && (
              <p className="text-muted-foreground py-6 text-center text-sm">
                {t("sales.cartEmpty")}
              </p>
            )}
          </div>
          {step === "items" && invalidLines.length > 0 && (
            <div
              role="alert"
              className="border-destructive/40 bg-destructive/10 text-destructive rounded-md border p-3 text-xs"
            >
              {t("sales.completeLineDetails")}
            </div>
          )}
          {step === "items" ? (
            <>
              <div className="flex items-end justify-between gap-2 border-t pt-3">
                <p className="text-muted-foreground text-sm">{t("sales.totalToPay")}</p>
                <p className="text-2xl font-bold tabular-nums">
                  <span>{money(subtotal)}</span>
                </p>
              </div>
              <Button
                className="w-full"
                size="lg"
                disabled={
                  !lines.length ||
                  missingLines.length > 0 ||
                  invalidLines.length > 0 ||
                  !saleLocation ||
                  locationsLoading ||
                  locationsError
                }
                onClick={() => setStep("confirm")}
              >
                {t("sales.reviewSale")}
              </Button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">{t("sales.reviewSale")}</h2>
                <Button variant="outline" size="sm" onClick={() => setStep("items")}>
                  {t("sales.backToItems")}
                </Button>
              </div>
              {saleLocation && (
                <p className="text-muted-foreground text-sm">
                  {t("sales.currentLocation", { location: saleLocation.name })}
                </p>
              )}
              <div className="space-y-1.5">
                <Label>{t("sales.customer")}</Label>
                <Select value={customerId} onValueChange={setCustomerId}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="comptoir">{t("sales.counterCustomer")}</SelectItem>
                    {(customers ?? []).map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {creditNeedsCustomer && (
                <p role="alert" className="text-destructive text-sm">
                  {t("sales.creditRequiresCustomer")}
                </p>
              )}
              {creditCustomerMissingPhone && (
                <p role="alert" className="text-destructive text-sm">
                  {t("sales.creditRequiresPhone")}
                </p>
              )}

              <div className="space-y-1.5">
                <Label>{t("sales.paymentMethod")}</Label>
                <Select value={payment} onValueChange={setPayment}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="especes">{t("sales.cash")}</SelectItem>
                    <SelectItem value="mobile_money">{t("sales.mobileMoney")}</SelectItem>
                    <SelectItem value="credit">{t("sales.credit")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {can("sales.manage") && (
                <div className="space-y-1.5">
                  <Label>{t("sales.discount")} (GNF)</Label>
                  <Input
                    type="number"
                    min="0"
                    max={subtotal}
                    aria-invalid={discountIsInvalid}
                    value={discount}
                    onChange={(e) => setDiscount(e.target.value)}
                  />
                  {discountIsInvalid && (
                    <p className="text-destructive text-xs">{t("sales.discountOutOfRange")}</p>
                  )}
                </div>
              )}

              <div className="space-y-1 border-t pt-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("sales.subtotal")}</span>
                  <span>{money(subtotal)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t("sales.discount")}</span>
                  <span>-{money(Number(discount || 0))}</span>
                </div>
                <div className="flex justify-between pt-1 text-lg font-bold">
                  <span>{t("sales.total")}</span>
                  <span>{money(total)}</span>
                </div>
              </div>
              {step === "items" && (
                <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-lg backdrop-blur lg:hidden">
                  <div className="mx-auto flex max-w-3xl items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-muted-foreground text-sm">
                        {t(cartQuantity === 1 ? "sales.cartCountOne" : "sales.cartCountMany", {
                          count: formatNumber(cartQuantity),
                        })}
                      </p>
                      <p className="truncate text-lg font-bold tabular-nums">{money(subtotal)}</p>
                    </div>
                    <Button
                      className="h-14 min-w-36 px-3 text-sm"
                      disabled={
                        !lines.length ||
                        missingLines.length > 0 ||
                        !saleLocation ||
                        locationsLoading ||
                        locationsError
                      }
                      onClick={() => setStep("confirm")}
                    >
                      {t("sales.reviewSale")}
                    </Button>
                  </div>
                </div>
              )}

              {missingLines.length > 0 && (
                <div className="border-destructive/40 bg-destructive/10 text-destructive rounded-md border p-3 text-xs">
                  {t("sales.exceedsStock", { count: missingLines.length })}
                </div>
              )}
              {invalidLines.length > 0 && (
                <div
                  role="alert"
                  className="border-destructive/40 bg-destructive/10 text-destructive rounded-md border p-3 text-xs"
                >
                  {t("sales.completeLineDetails")}
                </div>
              )}

              <Button
                className="w-full"
                size="lg"
                disabled={
                  !lines.length ||
                  !saleLocation ||
                  discountIsInvalid ||
                  invalidLines.length > 0 ||
                  missingLines.length > 0 ||
                  creditNeedsCustomer ||
                  creditCustomerMissingPhone ||
                  checkout.isPending
                }
                onClick={() => checkout.mutate()}
              >
                {checkout.isPending ? t("sales.savingSale") : t("sales.confirmSale")}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
