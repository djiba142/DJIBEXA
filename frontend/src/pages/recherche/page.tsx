import { useMutation } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { MapPin, Search, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { formatNumber, money } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/recherche")({
  validateSearch: (search: Record<string, unknown>) => ({
    q: typeof search.q === "string" ? search.q : "",
  }),
  head: () => ({
    meta: [
      { title: "Recherche intelligente — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Décrivez la pièce recherchée en texte libre : l'assistant retrouve les marchandises en stock avec quantité et emplacement.",
      },
      { property: "og:title", content: "Recherche intelligente — DJIBEXA" },
      {
        property: "og:description",
        content: "Trouvez une pièce en la décrivant simplement, avec son stock et son emplacement.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: RechercheIa,
});

const EXAMPLES = [
  "search.exampleBrakePads",
  "search.exampleOilFilter",
  "search.exampleShockAbsorber",
];

function RechercheIa() {
  const { t } = useLocale();
  const { hasRole } = useAuth();
  const { q } = PageRoute.useSearch();
  const [query, setQuery] = useState(q);

  const run = useMutation({
    mutationFn: async (q: string) => {
      type SearchProduct = {
        id: number;
        name: string;
        sku: string;
        alternative_references?: string;
        brand: string;
        vehicle: string;
        quantity: number;
        selling_price: string;
      };
      type SaleCatalogProduct = {
        id: number;
        name: string;
        sku: string;
        alternative_references: string;
        brand: string;
        vehicle: string;
        selling_price: string;
        stock_by_location: {
          location_id: number;
          location: string;
          quantity: number;
        }[];
      };
      type SearchStock = {
        product: number;
        location: number;
        location_name: string;
        quantity: number;
      };
      let products: SearchProduct[];
      let stocks: SearchStock[];
      let locations: { id: number; location_type: string }[];

      if (hasRole("sales") || hasRole("admin")) {
        const terms = q
          .normalize("NFD")
          .replace(/\p{Diacritic}/gu, "")
          .toLowerCase()
          .split(/\s+/)
          .filter((term) => term.length > 1);
        const catalogSearches = terms.length ? terms : [q.trim()];
        const catalogResults = await Promise.all(
          catalogSearches.map((term) =>
            api.list<SaleCatalogProduct>("sales/catalog/", { search: term }),
          ),
        );
        const catalog = [
          ...new Map(catalogResults.flat().map((product) => [product.id, product])).values(),
        ];
        products = catalog.map((product) => ({
          id: product.id,
          name: product.name,
          sku: product.sku,
          alternative_references: product.alternative_references,
          brand: product.brand,
          vehicle: product.vehicle,
          quantity: product.stock_by_location.reduce((total, stock) => total + stock.quantity, 0),
          selling_price: product.selling_price,
        }));
        stocks = catalog.flatMap((product) =>
          product.stock_by_location.map((stock) => ({
            product: product.id,
            location: stock.location_id,
            location_name: stock.location,
            quantity: stock.quantity,
          })),
        );
        locations = [...new Set(stocks.map((stock) => stock.location))].map((id) => ({
          id,
          location_type: "shop",
        }));
      } else {
        [products, stocks, locations] = await Promise.all([
          api.list<{
            id: number;
            name: string;
            sku: string;
            brand: string;
            vehicle: string;
            quantity: number;
            selling_price: string;
          }>("products/"),
          api.list<{ product: number; location: number; location_name: string; quantity: number }>(
            "inventory/stock/",
          ),
          api.list<{ id: number; location_type: string }>("inventory/locations/"),
        ]);
      }
      const terms = q
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase()
        .split(/\s+/)
        .filter((term) => term.length > 1);
      const matches = products
        .map((product) => {
          const content =
            `${product.name} ${product.sku} ${product.alternative_references ?? ""} ${product.brand} ${product.vehicle}`
              .normalize("NFD")
              .replace(/\p{Diacritic}/gu, "")
              .toLowerCase();
          const score = terms.filter((term) => content.includes(term)).length;
          const productStocks = stocks
            .filter((stock) => stock.product === product.id)
            .map((stock) => ({
              name: stock.location_name,
              quantity: stock.quantity,
              is_shop:
                locations.find((location) => location.id === stock.location)?.location_type ===
                "shop",
            }));
          return {
            id: String(product.id),
            name: product.name,
            reference: product.sku,
            brand: product.brand,
            vehicle: product.vehicle,
            stock: productStocks.reduce((total, stock) => total + stock.quantity, 0),
            sale_price: Number(product.selling_price),
            reason: "",
            score,
            locations: productStocks,
          };
        })
        .filter((product) => product.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 20);
      return { summary: t("search.summary", { count: formatNumber(matches.length) }), matches };
    },
  });
  const runSearch = run.mutate;

  useEffect(() => {
    const initialQuery = q.trim();
    if (initialQuery.length < 2) return;
    setQuery(initialQuery);
    runSearch(initialQuery);
  }, [q, runSearch]);

  function submit(q = query) {
    if (q.trim().length < 2 || run.isPending) return;
    setQuery(q);
    runSearch(q);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold uppercase">
          <Sparkles className="text-primary size-7" /> {t("search.title")}
        </h1>
        <p className="text-muted-foreground text-sm">{t("search.description")}</p>
      </div>

      <div className="panel space-y-3 p-4">
        <Label htmlFor="part-search" className="text-base font-semibold">
          {t("search.inputLabel")}
        </Label>
        <Input
          id="part-search"
          type="search"
          className="h-12 text-base"
          aria-describedby="part-search-help"
          placeholder={t("search.placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <p id="part-search-help" className="text-muted-foreground text-sm">
          {t("search.inputHelp")}
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((key) => (
              <Button key={key} variant="outline" size="sm" onClick={() => submit(t(key))}>
                {t(key)}
              </Button>
            ))}
          </div>
          <Button onClick={() => submit()} disabled={run.isPending || query.trim().length < 2}>
            <Search className="size-4" /> {run.isPending ? t("search.loading") : t("search.submit")}
          </Button>
        </div>
      </div>

      {run.isError && (
        <div className="panel text-destructive p-4 text-sm">
          {t("search.error")}: {run.error.message}
        </div>
      )}

      {run.data && (
        <div className="space-y-3">
          {run.data.summary && <p className="text-muted-foreground text-sm">{run.data.summary}</p>}
          {run.data.matches.length === 0 && (
            <div className="panel p-6 text-center text-sm">{t("search.none")}</div>
          )}
          {run.data.matches.map((m) => {
            const out = m.stock <= 0;
            return (
              <div
                key={m.id}
                className="panel flex flex-wrap items-start justify-between gap-4 p-4"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="font-semibold">{m.name}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {m.reference}
                    {m.brand ? ` · ${m.brand}` : ""}
                    {m.vehicle ? ` · ${m.vehicle}` : ""}
                  </p>
                  {m.reason && <p className="text-xs italic">{m.reason}</p>}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {m.locations.length ? (
                      m.locations.map((l) => (
                        <span
                          key={l.name}
                          className="bg-muted inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs"
                        >
                          <MapPin className="size-3" /> {l.name}
                          {l.is_shop ? ` (${t("search.shop")})` : ""} :{" "}
                          <strong>{l.quantity}</strong>
                        </span>
                      ))
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        {t("search.locationUnknown")}
                      </span>
                    )}
                  </div>
                </div>
                <div className="space-y-2 text-right">
                  <Badge variant={out ? "destructive" : "secondary"}>
                    {out ? t("search.out") : t("search.inStock", { count: formatNumber(m.stock) })}
                  </Badge>
                  <p className="font-semibold">{money(m.sale_price)}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
