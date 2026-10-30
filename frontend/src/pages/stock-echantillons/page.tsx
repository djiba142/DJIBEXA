import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/stock-echantillons")({
  head: () => ({
    meta: [
      { title: "Échantillons — ERP DJIBEXA" },
      {
        name: "description",
        content: "Suivi manuel et individuel des unités réservées comme échantillons.",
      },
    ],
  }),
  component: () => (
    <RequirePermission permission="stock.manage">
      <StockSamplesPage />
    </RequirePermission>
  ),
});

type ProductOption = {
  id: number;
  name: string;
  sku: string;
};

type StockUnit = {
  id: number;
  product: number;
  product_name: string;
  product_reference: string;
  location: number;
  location_name: string;
  carton_reference: string;
  unit_number: number;
  reference: string;
  status: string;
  is_separated: boolean;
};

type StockSummary = {
  product: number;
  location: number;
  quantity: number;
  sample_quantity: number;
  physical_quantity: number;
};

function StockSamplesPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [productSearch, setProductSearch] = useState("");
  const [selectedProduct, setSelectedProduct] = useState<ProductOption | null>(null);
  const [locationId, setLocationId] = useState("");
  const [unitSearch, setUnitSearch] = useState("");

  const productResults = useQuery({
    queryKey: ["sample-products", productSearch],
    enabled: productSearch.trim().length >= 2 && !selectedProduct,
    queryFn: () => api.list<ProductOption>("products/", { search: productSearch.trim() }),
  });
  const locations = useQuery({
    queryKey: ["sample-locations"],
    queryFn: () =>
      api.list<{ id: number; name: string; is_active: boolean }>("inventory/locations/"),
  });
  const stock = useQuery({
    queryKey: ["sample-stock"],
    queryFn: () => api.list<StockSummary>("inventory/stock/"),
  });
  const units = useQuery({
    queryKey: ["sample-units", selectedProduct?.id, locationId],
    enabled: !!selectedProduct && !!locationId,
    queryFn: () =>
      api.list<StockUnit>("inventory/units/", {
        product: selectedProduct!.id,
        location: Number(locationId),
      }),
  });

  const selectedStock = stock.data?.find(
    (row) => row.product === selectedProduct?.id && row.location === Number(locationId),
  );
  const visibleUnits = useMemo(() => {
    const query = unitSearch.trim().toLocaleLowerCase();
    if (!query) return units.data ?? [];
    return (units.data ?? []).filter(
      (unit) =>
        unit.reference.toLocaleLowerCase().includes(query) ||
        unit.carton_reference.toLocaleLowerCase().includes(query),
    );
  }, [unitSearch, units.data]);
  const availableCount = (units.data ?? []).filter((unit) => unit.status === "available").length;
  const sampleCount =
    selectedStock?.sample_quantity ??
    (units.data ?? []).filter((unit) => unit.status === "sample").length;
  const saleableCount = selectedStock?.quantity ?? 0;
  const physicalCount = selectedStock?.physical_quantity ?? saleableCount + sampleCount;
  const untrackedCount = Math.max(saleableCount - availableCount, 0);

  const initialize = useMutation({
    mutationFn: () => {
      if (!selectedProduct || !locationId) throw new Error(t("stockSamples.chooseBoth"));
      return api.post<{
        created_count: number;
        untracked_saleable_quantity: number;
      }>("inventory/units/initialize/", {
        product: selectedProduct.id,
        location: Number(locationId),
      });
    },
    onSuccess: (result) => {
      toast.success(t("stockSamples.initialized", { quantity: result.created_count }));
      void queryClient.invalidateQueries({ queryKey: ["sample-units"] });
      void queryClient.invalidateQueries({ queryKey: ["sample-stock"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const updateStatus = useMutation({
    mutationFn: ({ unit, status }: { unit: StockUnit; status: "sample" | "available" }) =>
      api.post(`inventory/units/${unit.id}/status/`, { status }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sample-units"] });
      void queryClient.invalidateQueries({ queryKey: ["sample-stock"] });
      void queryClient.invalidateQueries({ queryKey: ["products"] });
      void queryClient.invalidateQueries({ queryKey: ["stock"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-3xl font-bold uppercase">{t("stockSamples.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("stockSamples.description")}</p>
      </div>

      <div className="panel grid gap-4 p-5 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="sample-product-search">{t("stockSamples.product")}</Label>
          <div className="relative">
            <Search className="text-muted-foreground absolute top-2.5 left-3 size-4" />
            <Input
              id="sample-product-search"
              className="pl-9"
              placeholder={t("stockSamples.searchProduct")}
              value={productSearch}
              onChange={(event) => {
                setSelectedProduct(null);
                setProductSearch(event.target.value);
              }}
            />
          </div>
          {selectedProduct ? (
            <button
              type="button"
              className="w-full rounded border border-primary bg-primary/5 px-3 py-2 text-left text-sm"
              onClick={() => setSelectedProduct(null)}
            >
              <span className="font-medium">{selectedProduct.name}</span>
              <span className="text-muted-foreground ml-2 font-mono text-xs">
                {selectedProduct.sku}
              </span>
            </button>
          ) : (
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {(productResults.data ?? []).slice(0, 20).map((product) => (
                <button
                  key={product.id}
                  type="button"
                  className="hover:bg-muted w-full rounded border px-3 py-2 text-left text-sm"
                  onClick={() => {
                    setSelectedProduct(product);
                    setProductSearch(`${product.name} · ${product.sku}`);
                    setUnitSearch("");
                  }}
                >
                  <span className="font-medium">{product.name}</span>
                  <span className="text-muted-foreground ml-2 font-mono text-xs">
                    {product.sku}
                  </span>
                </button>
              ))}
              {productSearch.trim().length >= 2 && productResults.data?.length === 0 && (
                <p className="text-muted-foreground px-2 py-1 text-sm">
                  {t("stockSamples.noProducts")}
                </p>
              )}
              {productResults.isError && (
                <p className="text-destructive px-2 py-1 text-sm">
                  {t("stockSamples.productsError")}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label>{t("stockSamples.location")}</Label>
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger>
              <SelectValue placeholder={t("stockSamples.chooseLocation")} />
            </SelectTrigger>
            <SelectContent>
              {(locations.data ?? [])
                .filter((location) => location.is_active)
                .map((location) => (
                  <SelectItem key={location.id} value={String(location.id)}>
                    {location.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {selectedProduct && locationId && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <QuantityCard title={t("stockSamples.saleable")} value={saleableCount} />
            <QuantityCard title={t("stockSamples.samples")} value={sampleCount} />
            <QuantityCard title={t("stockSamples.physical")} value={physicalCount} />
          </div>

          <div className="panel space-y-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="font-semibold">{t("stockSamples.unitsTitle")}</h2>
                <p className="text-muted-foreground text-sm">
                  {t("stockSamples.unitsDescription")}
                </p>
              </div>
              <Button
                variant="outline"
                disabled={initialize.isPending}
                onClick={() => initialize.mutate()}
              >
                <RefreshCw className="size-4" />
                {initialize.isPending
                  ? t("stockSamples.initializing")
                  : t("stockSamples.trackUnits")}
              </Button>
            </div>

            {untrackedCount > 0 && (
              <p className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                {t("stockSamples.untrackedWarning", { quantity: untrackedCount })}
              </p>
            )}

            <div className="max-w-sm">
              <Label htmlFor="sample-unit-search">{t("stockSamples.searchUnit")}</Label>
              <Input
                id="sample-unit-search"
                value={unitSearch}
                onChange={(event) => setUnitSearch(event.target.value)}
                placeholder={t("stockSamples.searchUnitPlaceholder")}
              />
            </div>

            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("stockSamples.unitReference")}</TableHead>
                    <TableHead>{t("stockSamples.cartonReference")}</TableHead>
                    <TableHead>{t("stockSamples.status")}</TableHead>
                    <TableHead className="text-right">{t("stockSamples.action")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleUnits.map((unit) => (
                    <TableRow key={unit.id}>
                      <TableCell className="font-mono text-xs">{unit.reference}</TableCell>
                      <TableCell className="font-mono text-xs">{unit.carton_reference}</TableCell>
                      <TableCell>
                        <Badge variant={unit.status === "sample" ? "secondary" : "outline"}>
                          {t(`stockSamples.status.${unit.status}`)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {unit.status === "available" || unit.status === "sample" ? (
                          <Button
                            size="sm"
                            variant={unit.status === "sample" ? "outline" : "default"}
                            disabled={updateStatus.isPending}
                            onClick={() =>
                              updateStatus.mutate({
                                unit,
                                status: unit.status === "sample" ? "available" : "sample",
                              })
                            }
                          >
                            {unit.status === "sample"
                              ? t("stockSamples.returnToSale")
                              : t("stockSamples.markSample")}
                          </Button>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {!units.isLoading && !visibleUnits.length && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-muted-foreground py-8 text-center">
                        {units.isError ? t("stockSamples.unitsError") : t("stockSamples.noUnits")}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function QuantityCard({ title, value }: { title: string; value: number }) {
  return (
    <div className="panel p-4">
      <p className="text-muted-foreground text-sm">{title}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
