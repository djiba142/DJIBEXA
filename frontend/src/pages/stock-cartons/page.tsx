import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Package, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { RequirePermission } from "@/components/RequirePermission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
import { dateTime, formatNumber } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/stock-cartons")({
  head: () => ({
    meta: [
      { title: "Cartons et lots — ERP DJIBEXA" },
      { name: "description", content: "Suivi des quantités et mouvements par carton ou lot." },
    ],
  }),
  component: () => (
    <RequirePermission permission="stock.view">
      <StockCartons />
    </RequirePermission>
  ),
});

type CartonRow = {
  id: number;
  product_name: string;
  product_reference: string;
  product: number;
  location_name: string;
  location: number;
  reference: string;
  qr_code?: string;
  receipt_reference?: string | null;
  supplier_reference?: string;
  quantity: number;
  initial_quantity: number;
  status: string;
};

type CartonMovement = {
  type: string;
  reference: string;
  quantity: number;
  quantity_received?: number | null;
  from_location: string | null;
  to_location: string | null;
  status: string;
  created_at: string;
};

type CartonHistory = {
  carton: string;
  product: number;
  location: string;
  quantity: number;
  initial_quantity: number;
  movements: CartonMovement[];
};

function StockCartons() {
  const { t } = useLocale();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [locationFilter, setLocationFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const {
    data: cartons,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["inventory-cartons"],
    queryFn: () => api.list<CartonRow>("inventory/cartons/"),
  });
  const {
    data: history,
    isLoading: historyLoading,
    isError: historyError,
  } = useQuery({
    queryKey: ["inventory-carton-history", selectedId],
    enabled: selectedId !== null,
    queryFn: () => api.get<CartonHistory>(`inventory/cartons/${selectedId}/movements/`),
  });
  const selectedCarton = cartons?.find((carton) => carton.id === selectedId);
  const locations = useMemo(
    () =>
      Array.from(
        new Map((cartons ?? []).map((carton) => [carton.location, carton.location_name])).entries(),
      ),
    [cartons],
  );
  const visibleCartons = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (cartons ?? []).filter((carton) => {
      const matchesLocation =
        locationFilter === "all" || String(carton.location) === locationFilter;
      const matchesStatus = statusFilter === "all" || carton.status === statusFilter;
      const matchesSearch =
        !query ||
        [
          carton.product_name,
          carton.product_reference,
          carton.reference,
          carton.qr_code ?? "",
          carton.receipt_reference ?? "",
          carton.supplier_reference ?? "",
          carton.location_name,
        ].some((value) => value.toLocaleLowerCase().includes(query));
      return matchesLocation && matchesStatus && matchesSearch;
    });
  }, [cartons, locationFilter, search, statusFilter]);
  const remainingPieces = (cartons ?? []).reduce((total, carton) => total + carton.quantity, 0);
  const statusKeys = [
    "en_stock",
    "boutique",
    "en_transit",
    "partiellement_utilise",
    "vide",
  ] as const;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header>
        <h1 className="text-3xl font-bold uppercase">{t("stockCartons.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("stockCartons.description")}</p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2" aria-label={t("stockCartons.summary")}>
        <div className="panel p-4">
          <p className="text-muted-foreground text-xs tracking-widest uppercase">
            {t("stockCartons.trackedCartons")}
          </p>
          <p className="text-2xl font-bold">{formatNumber(cartons?.length ?? 0)}</p>
        </div>
        <div className="panel p-4">
          <p className="text-muted-foreground text-xs tracking-widest uppercase">
            {t("stockCartons.remainingPieces")}
          </p>
          <p className="text-2xl font-bold">{formatNumber(remainingPieces)}</p>
        </div>
      </section>

      <div className="panel overflow-x-auto">
        <div className="grid gap-3 border-b p-3 md:grid-cols-[minmax(12rem,1fr)_minmax(10rem,0.6fr)_minmax(10rem,0.6fr)_auto]">
          <div className="space-y-1.5">
            <Label htmlFor="carton-search">{t("stockCartons.search")}</Label>
            <div className="relative">
              <Search className="text-muted-foreground absolute top-2.5 left-3 size-4" />
              <Input
                id="carton-search"
                className="pl-9"
                placeholder={t("stockCartons.searchPlaceholder")}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>{t("stockCartons.location")}</Label>
            <Select value={locationFilter} onValueChange={setLocationFilter}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("stockCartons.allLocations")}</SelectItem>
                {locations.map(([id, name]) => (
                  <SelectItem key={id} value={String(id)}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>{t("stockCartons.status")}</Label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("stockCartons.allStates")}</SelectItem>
                {statusKeys.map((status) => (
                  <SelectItem key={status} value={status}>
                    {t(`stockCartons.state.${status}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => void refetch()}
              disabled={isLoading}
            >
              <RefreshCw className="size-4" />
              {t("stockCartons.refresh")}
            </Button>
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventory.product")}</TableHead>
              <TableHead>{t("stockCartons.reference")}</TableHead>
              <TableHead>{t("stock.location")}</TableHead>
              <TableHead className="text-right">{t("stockCartons.quantity")}</TableHead>
              <TableHead>{t("stockCartons.status")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleCartons.map((carton) => (
              <TableRow
                key={carton.id}
                className="cursor-pointer"
                onClick={() => setSelectedId(carton.id)}
              >
                <TableCell>
                  <p className="font-medium">{carton.product_name}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {carton.product_reference}
                  </p>
                </TableCell>
                <TableCell className="font-mono text-xs">{carton.reference}</TableCell>
                <TableCell>{carton.location_name}</TableCell>
                <TableCell className="text-right">
                  {formatNumber(carton.quantity)} / {formatNumber(carton.initial_quantity)}
                </TableCell>
                <TableCell>
                  <Badge variant={carton.quantity > 0 ? "secondary" : "outline"}>
                    {t(`stockCartons.state.${carton.status}`)}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && !isError && !cartons?.length && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center">
                  <div className="mx-auto flex max-w-md flex-col items-center gap-3">
                    <Package className="text-muted-foreground size-8" />
                    <p className="font-medium">{t("stockCartons.empty")}</p>
                    <p className="text-muted-foreground text-sm">
                      {t("stockCartons.emptyDescription")}
                    </p>
                    <Button asChild variant="outline">
                      <Link to="/receptions/">{t("stockCartons.openReceipts")}</Link>
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !isError && !!cartons?.length && !visibleCartons.length && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-10 text-center">
                  {t("stockCartons.noResults")}
                </TableCell>
              </TableRow>
            )}
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-10 text-center">
                  {t("reports.loading")}
                </TableCell>
              </TableRow>
            )}
            {isError && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center">
                  <p className="text-destructive mb-3">{t("stockCartons.loadError")}</p>
                  <Button type="button" variant="outline" onClick={() => void refetch()}>
                    <RefreshCw className="size-4" />
                    {t("stockCartons.retry")}
                  </Button>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={selectedId !== null} onOpenChange={(open) => !open && setSelectedId(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{selectedCarton?.reference ?? t("stockCartons.history")}</DialogTitle>
          </DialogHeader>
          {selectedCarton && (
            <div className="grid gap-3 rounded-md border p-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-muted-foreground">{t("inventory.product")}</p>
                <p className="font-medium">{selectedCarton.product_name}</p>
                <p className="text-muted-foreground font-mono text-xs">
                  {selectedCarton.product_reference}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">{t("stockCartons.location")}</p>
                <p className="font-medium">{selectedCarton.location_name}</p>
              </div>
              <div>
                <p className="text-muted-foreground">{t("stockCartons.quantity")}</p>
                <p className="font-medium">
                  {formatNumber(selectedCarton.quantity)} /{" "}
                  {formatNumber(selectedCarton.initial_quantity)}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">{t("stockCartons.status")}</p>
                <p className="font-medium">{t(`stockCartons.state.${selectedCarton.status}`)}</p>
              </div>
              {selectedCarton.receipt_reference && (
                <div>
                  <p className="text-muted-foreground">{t("stockCartons.receipt")}</p>
                  <p className="font-mono text-xs">{selectedCarton.receipt_reference}</p>
                </div>
              )}
              {selectedCarton.qr_code && (
                <div>
                  <p className="text-muted-foreground">{t("stockCartons.qrCode")}</p>
                  <p className="font-mono text-xs">{selectedCarton.qr_code}</p>
                </div>
              )}
            </div>
          )}
          {historyLoading && (
            <p className="text-muted-foreground text-sm">{t("reports.loading")}</p>
          )}
          {historyError && (
            <p className="text-destructive text-sm">{t("stockCartons.historyError")}</p>
          )}
          <div className="max-h-[60vh] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("stockCartons.date")}</TableHead>
                  <TableHead>{t("stockCartons.event")}</TableHead>
                  <TableHead>{t("stockCartons.reference")}</TableHead>
                  <TableHead>{t("stockCartons.route")}</TableHead>
                  <TableHead className="text-right">{t("stockCartons.quantity")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(history?.movements ?? []).map((movement, index) => (
                  <TableRow key={`${movement.reference}-${index}`}>
                    <TableCell className="whitespace-nowrap text-xs">
                      {dateTime(movement.created_at)}
                    </TableCell>
                    <TableCell>{t(`stockCartons.event.${movement.type}`)}</TableCell>
                    <TableCell className="font-mono text-xs">{movement.reference}</TableCell>
                    <TableCell className="text-xs">
                      {[movement.from_location, movement.to_location].filter(Boolean).join(" → ") ||
                        "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatNumber(movement.quantity)}
                      {movement.quantity_received !== undefined &&
                        movement.quantity_received !== null &&
                        ` / ${formatNumber(movement.quantity_received)}`}
                    </TableCell>
                  </TableRow>
                ))}
                {!historyLoading && !historyError && !history?.movements.length && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                      {t("stockCartons.noMovements")}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
