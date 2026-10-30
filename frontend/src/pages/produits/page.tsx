import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { formatNumber, money } from "@/lib/format";
import { useLocale } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/produits")({
  head: () => ({
    meta: [
      { title: "Produits — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Catalogue des pièces détachées : références, marques, prix d'achat et de vente, stock disponible.",
      },
      { property: "og:title", content: "Produits — DJIBEXA" },
      { property: "og:description", content: "Gestion du catalogue de pièces détachées." },
    ],
  }),
  component: Produits,
});

const empty = {
  reference: "",
  manufacturer_reference: "",
  alternative_references: "",
  name: "",
  category_id: "",
  brand: "",
  vehicle: "",
  description: "",
  image: "",
  unit: "piece",
  package_unit: "",
  units_per_package: "",
  purchase_price: "",
  cost_price: "",
  sale_price: "",
  alert_threshold: "5",
};

const PAGE_SIZE = 25;

type CategoryRow = { id: number; name: string };
type CatalogImportPreview = {
  id: number;
  source_name: string;
  headers: string[];
  mapping: Record<string, string>;
  fields: string[];
  unknown_columns: string[];
  rows: {
    line: number;
    action: "create" | "update";
    values: Record<string, string | number | null>;
    unknown_values: Record<string, string | null>;
    errors: string[];
    warnings: string[];
  }[];
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  category_review_rows: number;
};
type ProductRow = {
  id: string;
  category_id: string | null;
  categories: { name: string } | null;
  reference: string;
  manufacturer_reference: string;
  alternative_references: string;
  name: string;
  brand: string;
  vehicle: string;
  description: string;
  image: string;
  unit: string;
  package_unit: string;
  units_per_package: number | null;
  purchase_price: number;
  cost_price: number;
  sale_price: number;
  stock: number;
  alert_threshold: number;
};

function Produits() {
  const { t } = useLocale();
  const { can, hasRole } = useAuth();
  const canManageProducts = can("products.manage");
  const isAdmin = hasRole("admin");
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [stockFilter, setStockFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ ...empty });
  const [editing, setEditing] = useState<ProductRow | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importPreview, setImportPreview] = useState<CatalogImportPreview | null>(null);
  const [createImportCategories, setCreateImportCategories] = useState(false);

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => api.list<CategoryRow>("products/categories/"),
  });

  const { data: products } = useQuery({
    queryKey: ["products"],
    queryFn: async () =>
      (
        await api.list<{
          id: number;
          category: number | null;
          category_name: string | null;
          sku: string;
          manufacturer_reference: string;
          alternative_references: string;
          name: string;
          brand: string;
          vehicle: string;
          description: string;
          image: string;
          unit: string;
          package_unit: string;
          units_per_package: number | null;
          purchase_price?: string;
          cost_price?: string;
          selling_price: string;
          quantity: number;
          alert_threshold: number;
        }>("products/")
      ).map((product): ProductRow => ({
        id: String(product.id),
        category_id: product.category === null ? null : String(product.category),
        categories: product.category_name ? { name: product.category_name } : null,
        reference: product.sku,
        manufacturer_reference: product.manufacturer_reference,
        alternative_references: product.alternative_references,
        name: product.name,
        brand: product.brand,
        vehicle: product.vehicle,
        description: product.description,
        image: product.image,
        unit: product.unit,
        package_unit: product.package_unit,
        units_per_package: product.units_per_package,
        purchase_price: Number(product.purchase_price ?? 0),
        cost_price: Number(product.cost_price ?? 0),
        sale_price: Number(product.selling_price),
        stock: product.quantity,
        alert_threshold: product.alert_threshold,
      })),
  });

  const saveProduct = useMutation({
    mutationFn: async () => {
      const payload = {
        sku: form.reference.trim(),
        manufacturer_reference: form.manufacturer_reference.trim(),
        alternative_references: form.alternative_references
          .split(/[,\n]/)
          .map((reference) => reference.trim())
          .filter(Boolean)
          .join("\n"),
        name: form.name.trim(),
        category: form.category_id ? Number(form.category_id) : null,
        brand: form.brand.trim(),
        vehicle: form.vehicle.trim(),
        description: form.description.trim(),
        image: form.image.trim(),
        unit: form.unit,
        package_unit: form.package_unit,
        units_per_package: form.package_unit ? Number(form.units_per_package) : null,
        ...(isAdmin
          ? {
              purchase_price: Number(form.purchase_price || 0),
              cost_price: Number(form.cost_price || 0),
            }
          : {}),
        selling_price: Number(form.sale_price || 0),
        alert_threshold: Number(form.alert_threshold || 0),
        currency: "GNF",
      };
      if (editing) {
        await api.patch(`products/${editing.id}/`, payload);
      } else {
        await api.post("products/", payload);
      }
    },
    onSuccess: () => {
      toast.success(t(editing ? "products.updated" : "products.added"));
      setForm({ ...empty });
      setEditing(null);
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["products"] });
    },
    onError: (e: Error) => toast.error(t("products.saveError"), { description: e.message }),
  });

  const previewCatalogImport = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return api.post<CatalogImportPreview>("products/catalog-import/", body);
    },
    onSuccess: (preview) => setImportPreview(preview),
    onError: (error: Error) =>
      toast.error(t("products.importFileError"), { description: error.message }),
  });

  const mapCatalogColumns = useMutation({
    mutationFn: (mapping: Record<string, string>) =>
      api.post<CatalogImportPreview>(`products/catalog-import/${importPreview?.id}/mapping/`, {
        mapping,
      }),
    onSuccess: setImportPreview,
    onError: (error: Error) =>
      toast.error(t("products.importMappingError"), { description: error.message }),
  });

  const confirmCatalogImport = useMutation({
    mutationFn: () =>
      api.post<{ summary: { created: number; updated: number; skipped: number; errors: number } }>(
        `products/catalog-import/${importPreview?.id}/confirm/`,
        { create_categories: createImportCategories },
      ),
    onSuccess: (result) => {
      toast.success(
        t("products.catalogImportSuccess", {
          count: result.summary.created,
          updated: result.summary.updated,
        }),
      );
      setImportOpen(false);
      setImportPreview(null);
      setCreateImportCategories(false);
      void qc.invalidateQueries({ queryKey: ["products"] });
      void qc.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (error: Error) =>
      toast.error(t("products.catalogImportError"), { description: error.message }),
  });

  function editProduct(product: ProductRow) {
    setEditing(product);
    setForm({
      ...empty,
      reference: product.reference,
      manufacturer_reference: product.manufacturer_reference,
      alternative_references: product.alternative_references.replace(/\n/g, ", "),
      name: product.name,
      category_id: product.category_id ?? "",
      brand: product.brand,
      vehicle: product.vehicle,
      description: product.description,
      image: product.image,
      unit: product.unit,
      package_unit: product.package_unit,
      units_per_package: product.units_per_package ? String(product.units_per_package) : "",
      purchase_price: String(product.purchase_price),
      cost_price: String(product.cost_price),
      sale_price: String(product.sale_price),
      alert_threshold: String(product.alert_threshold),
    });
    setOpen(true);
  }

  const matched = (products ?? []).filter((p) => {
    const text =
      `${p.name} ${p.reference} ${p.manufacturer_reference} ${p.alternative_references} ${p.brand ?? ""} ${p.vehicle ?? ""}`.toLowerCase();
    if (!text.includes(search.toLowerCase())) return false;
    if (category !== "all" && p.category_id !== category) return false;
    if (stockFilter === "rupture" && p.stock > 0) return false;
    if (stockFilter === "alerte" && !(p.stock > 0 && p.stock <= p.alert_threshold)) return false;
    if (stockFilter === "dispo" && p.stock <= p.alert_threshold) return false;
    return true;
  });

  const pageCount = Math.max(1, Math.ceil(matched.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const filtered = matched.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("products.title")}</h1>
          <p className="text-muted-foreground text-sm">
            {t("products.count", { count: formatNumber(matched.length) })}
          </p>
        </div>

        {canManageProducts && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setImportPreview(null);
                setImportOpen(true);
              }}
            >
              {t("products.import")}
            </Button>
            <Dialog
              open={open}
              onOpenChange={(nextOpen) => {
                setOpen(nextOpen);
                if (!nextOpen) {
                  setEditing(null);
                  setForm({ ...empty });
                }
              }}
            >
              <DialogTrigger asChild>
                <Button
                  onClick={() => {
                    setEditing(null);
                    setForm({ ...empty });
                  }}
                >
                  {t("products.add")}
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>{t(editing ? "products.edit" : "products.new")}</DialogTitle>
                </DialogHeader>
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide">
                    {t("products.identificationSection")}
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label={`${t("products.internalReference")} *`}>
                      <Input
                        value={form.reference}
                        onChange={(e) => setForm({ ...form, reference: e.target.value })}
                      />
                    </Field>
                    <Field label={`${t("products.name")} *`}>
                      <Input
                        value={form.name}
                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                      />
                    </Field>
                    <Field label={t("products.manufacturerReference")}>
                      <Input
                        value={form.manufacturer_reference}
                        onChange={(e) =>
                          setForm({ ...form, manufacturer_reference: e.target.value })
                        }
                      />
                    </Field>
                    <Field label={t("products.alternativeReferences")}>
                      <Input
                        value={form.alternative_references}
                        placeholder={t("products.alternativeReferencesPlaceholder")}
                        onChange={(e) =>
                          setForm({ ...form, alternative_references: e.target.value })
                        }
                      />
                    </Field>
                    <Field label={t("products.category")}>
                      <Select
                        value={form.category_id || "none"}
                        onValueChange={(value) =>
                          setForm({ ...form, category_id: value === "none" ? "" : value })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder={t("products.choose")} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t("products.choose")}</SelectItem>
                          {(categories ?? []).map((c) => (
                            <SelectItem key={c.id} value={String(c.id)}>
                              {c.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label={t("products.brand")}>
                      <Input
                        value={form.brand}
                        onChange={(e) => setForm({ ...form, brand: e.target.value })}
                      />
                    </Field>
                    <Field label={t("products.vehicle")}>
                      <Input
                        value={form.vehicle}
                        onChange={(e) => setForm({ ...form, vehicle: e.target.value })}
                      />
                    </Field>
                    <Field label={t("products.description")}>
                      <Textarea
                        value={form.description}
                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                      />
                    </Field>
                    <Field label={t("products.imageUrl")}>
                      <Input
                        type="url"
                        value={form.image}
                        onChange={(e) => setForm({ ...form, image: e.target.value })}
                      />
                    </Field>
                  </div>
                </section>
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide">
                    {t("products.stockSection")}
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label={t("products.unit")}>
                      <Select
                        value={form.unit}
                        onValueChange={(unit) => setForm({ ...form, unit })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {["piece", "pair", "set", "liter"].map((unit) => (
                            <SelectItem key={unit} value={unit}>
                              {t(`products.unit.${unit}`)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label={t("products.packageUnit")}>
                      <Select
                        value={form.package_unit || "none"}
                        onValueChange={(package_unit) =>
                          setForm({
                            ...form,
                            package_unit: package_unit === "none" ? "" : package_unit,
                            units_per_package:
                              package_unit === "none" ? "" : form.units_per_package,
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t("products.noPackage")}</SelectItem>
                          <SelectItem value="carton">{t("products.package.carton")}</SelectItem>
                          <SelectItem value="box">{t("products.package.box")}</SelectItem>
                          <SelectItem value="pack">{t("products.package.pack")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    {form.package_unit && (
                      <Field label={t("products.unitsPerPackage")}>
                        <Input
                          type="number"
                          min={1}
                          step={1}
                          value={form.units_per_package}
                          onChange={(e) => setForm({ ...form, units_per_package: e.target.value })}
                        />
                      </Field>
                    )}
                    <Field label={t("products.alertThreshold")}>
                      <Input
                        type="number"
                        min={0}
                        step={1}
                        value={form.alert_threshold}
                        onChange={(e) => setForm({ ...form, alert_threshold: e.target.value })}
                      />
                    </Field>
                  </div>
                  {editing && (
                    <p className="text-muted-foreground text-xs">
                      {t("products.stockMovementOnly")}
                    </p>
                  )}
                </section>
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wide">
                    {t("products.pricingSection")}
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {isAdmin && (
                      <>
                        <Field label={t("products.purchasePrice")}>
                          <Input
                            type="number"
                            min={0}
                            step="0.01"
                            value={form.purchase_price}
                            onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                          />
                        </Field>
                        <Field label={t("products.costPrice")}>
                          <Input
                            type="number"
                            min={0}
                            step="0.01"
                            value={form.cost_price}
                            onChange={(e) => setForm({ ...form, cost_price: e.target.value })}
                          />
                        </Field>
                      </>
                    )}
                    <Field label={t("products.salePrice")}>
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={form.sale_price}
                        onChange={(e) => setForm({ ...form, sale_price: e.target.value })}
                      />
                    </Field>
                    {isAdmin && form.cost_price && form.sale_price && (
                      <p className="text-muted-foreground self-end text-sm">
                        {t("products.estimatedMargin")}:{" "}
                        {money(Number(form.sale_price) - Number(form.cost_price))}
                      </p>
                    )}
                  </div>
                </section>
                <DialogFooter>
                  <Button
                    onClick={() => saveProduct.mutate()}
                    disabled={
                      !form.reference ||
                      !form.name ||
                      (Boolean(form.package_unit) && !form.units_per_package) ||
                      saveProduct.isPending
                    }
                  >
                    {t("common.save")}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        )}
      </div>

      {canManageProducts && (
        <Dialog
          open={importOpen}
          onOpenChange={(nextOpen) => {
            setImportOpen(nextOpen);
            if (!nextOpen) {
              setImportPreview(null);
              setCreateImportCategories(false);
            }
          }}
        >
          <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t("products.catalogImportTitle")}</DialogTitle>
              <p className="text-muted-foreground text-sm">
                {t("products.catalogImportDescription")}
              </p>
            </DialogHeader>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  void api
                    .download("products/catalog-import/template/", "modele-produits-djibexa.csv")
                    .catch((error: Error) =>
                      toast.error(t("products.importFileError"), { description: error.message }),
                    )
                }
              >
                {t("products.downloadCatalogTemplate")}
              </Button>
              <Input
                type="file"
                accept=".csv,.xlsx"
                disabled={previewCatalogImport.isPending}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) previewCatalogImport.mutate(file);
                  event.currentTarget.value = "";
                }}
                className="max-w-sm"
              />
            </div>
            {importPreview && (
              <div className="space-y-4">
                <div className="rounded-md border p-3 text-sm">
                  <strong>{importPreview.source_name}</strong>
                  <span className="ml-3">{importPreview.total_rows} ligne(s)</span>
                  <span className="ml-3 text-emerald-700">
                    {t("products.importReady", { count: importPreview.valid_rows })}
                  </span>
                  {importPreview.error_rows > 0 && (
                    <span className="ml-3 text-destructive">
                      {t("products.importErrors", { count: importPreview.error_rows })}
                    </span>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {importPreview.headers.map((header) => (
                    <Field key={header} label={t("products.importColumn", { name: header })}>
                      <Select
                        disabled={mapCatalogColumns.isPending}
                        value={importPreview.mapping[header] || "ignore"}
                        onValueChange={(field) => {
                          const mapping = { ...importPreview.mapping };
                          if (field === "ignore") mapping[header] = "";
                          else mapping[header] = field;
                          mapCatalogColumns.mutate(mapping);
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Ignorer cette colonne" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ignore">{t("products.ignoreColumn")}</SelectItem>
                          {importPreview.fields.map((field) => (
                            <SelectItem key={field} value={field}>
                              {field}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </Field>
                  ))}
                </div>
                {isAdmin && importPreview.category_review_rows > 0 && (
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={createImportCategories}
                      onChange={(event) => setCreateImportCategories(event.target.checked)}
                    />
                    {t("products.createImportCategories")}
                  </label>
                )}
                {!isAdmin && importPreview.category_review_rows > 0 && (
                  <p className="text-sm text-amber-700">{t("products.unknownCategoryAdminHint")}</p>
                )}
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("products.importLine")}</TableHead>
                        <TableHead>{t("products.importAction")}</TableHead>
                        <TableHead>Référence</TableHead>
                        <TableHead>Désignation</TableHead>
                        <TableHead>Catégorie</TableHead>
                        <TableHead>{t("products.importReviewResult")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {importPreview.rows.map((row) => (
                        <TableRow key={row.line}>
                          <TableCell>{row.line}</TableCell>
                          <TableCell>
                            {t(
                              row.action === "update"
                                ? "products.importUpdate"
                                : "products.importCreate",
                            )}
                          </TableCell>
                          <TableCell>{String(row.values.sku ?? "—")}</TableCell>
                          <TableCell>{String(row.values.name ?? "—")}</TableCell>
                          <TableCell>{String(row.values.category ?? "—")}</TableCell>
                          <TableCell className="text-sm">
                            {row.errors.length
                              ? row.errors.join(" ")
                              : row.values.category_status === "existante"
                                ? t("products.categoryExisting")
                                : row.values.category_status === "à créer ou corriger"
                                  ? t("products.categoryNeedsReview")
                                  : t("products.categoryNotSet")}
                            {row.warnings.length > 0 && (
                              <span className="block text-amber-700">
                                {t("products.importPriceWarning")}
                              </span>
                            )}
                            {Object.keys(row.unknown_values).length > 0 && (
                              <span className="block text-muted-foreground">
                                {t("products.ignoredColumns", {
                                  columns: Object.keys(row.unknown_values).join(", "),
                                })}
                              </span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  {importPreview.total_rows > importPreview.rows.length && (
                    <p className="text-muted-foreground p-3 text-sm">
                      {t("products.previewLimit", {
                        count: importPreview.rows.length,
                        total: importPreview.total_rows,
                      })}
                    </p>
                  )}
                </div>
              </div>
            )}
            <DialogFooter>
              <Button
                disabled={
                  !importPreview ||
                  importPreview.valid_rows !== importPreview.total_rows ||
                  importPreview.total_rows === 0 ||
                  (importPreview.category_review_rows > 0 &&
                    (!isAdmin || !createImportCategories)) ||
                  mapCatalogColumns.isPending ||
                  confirmCatalogImport.isPending
                }
                onClick={() => confirmCatalogImport.mutate()}
              >
                {confirmCatalogImport.isPending
                  ? t("products.importing")
                  : t("products.importConfirm")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <div className="panel grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
        <Input
          placeholder={t("products.search")}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          className="xl:col-span-2"
        />
        <Select
          value={category}
          onValueChange={(v) => {
            setCategory(v);
            setPage(0);
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder={t("products.category")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("products.allCategories")}</SelectItem>
            {(categories ?? []).map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={stockFilter}
          onValueChange={(v) => {
            setStockFilter(v);
            setPage(0);
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder={t("nav.stock")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("products.allStock")}</SelectItem>
            <SelectItem value="dispo">{t("products.available")}</SelectItem>
            <SelectItem value="alerte">{t("products.belowThreshold")}</SelectItem>
            <SelectItem value="rupture">{t("products.outOfStock")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("products.reference")}</TableHead>
              <TableHead>{t("products.name")}</TableHead>
              <TableHead className="hidden md:table-cell">{t("products.category")}</TableHead>
              <TableHead className="hidden lg:table-cell">{t("products.vehicle")}</TableHead>
              <TableHead className="text-right">{t("products.salePrice")}</TableHead>
              <TableHead className="text-right">{t("nav.stock")}</TableHead>
              {canManageProducts && (
                <TableHead className="text-right">{t("common.actions")}</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-mono text-xs">
                  <div>{p.reference}</div>
                  {p.manufacturer_reference && (
                    <div className="text-muted-foreground font-sans">
                      {t("products.manufacturerReferenceShort")}: {p.manufacturer_reference}
                    </div>
                  )}
                </TableCell>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell className="hidden md:table-cell">{p.categories?.name ?? "—"}</TableCell>
                <TableCell className="hidden lg:table-cell">{p.vehicle ?? "—"}</TableCell>
                <TableCell className="text-right">{money(p.sale_price)}</TableCell>
                <TableCell className="text-right">
                  <Badge
                    variant={
                      p.stock === 0
                        ? "destructive"
                        : p.stock <= p.alert_threshold
                          ? "secondary"
                          : "outline"
                    }
                  >
                    {p.package_unit && p.units_per_package
                      ? `${Math.floor(p.stock / p.units_per_package)} ${t(`products.package.${p.package_unit}`)} + ${p.stock % p.units_per_package} ${t(`products.unit.${p.unit}`)}`
                      : `${p.stock} ${t(`products.unit.${p.unit}`)}`}
                  </Badge>
                </TableCell>
                {canManageProducts && (
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" onClick={() => editProduct(p)}>
                      {t("common.edit")}
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {!filtered.length && (
              <TableRow>
                <TableCell
                  colSpan={canManageProducts ? 7 : 6}
                  className="text-muted-foreground py-10 text-center"
                >
                  {t("products.none")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-muted-foreground text-sm">
            {t("products.page", { current: currentPage + 1, total: pageCount })}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage === 0}
              onClick={() => setPage(currentPage - 1)}
            >
              {t("common.previous")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage >= pageCount - 1}
              onClick={() => setPage(currentPage + 1)}
            >
              {t("common.next")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
