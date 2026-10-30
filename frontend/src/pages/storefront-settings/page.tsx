import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Eye, Globe2, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { StorefrontContent } from "@/pages/company-storefront/public-api";

export const PageRoute = createFileRoute("/_authenticated/vitrine")({
  head: () => ({
    meta: [
      { title: "Vitrine publique — ERP DJIBEXA" },
      {
        name: "description",
        content: "Configurez, prévisualisez et publiez la vitrine de votre entreprise.",
      },
    ],
  }),
  component: StorefrontSettingsPage,
});

type StorefrontSettings = {
  tenant_slug: string;
  draft: StorefrontContent;
  published: StorefrontContent | Record<string, never>;
  draft_assets: { logo: boolean; cover: boolean };
  published_assets: { logo: boolean; cover: boolean };
  published_at: string | null;
  is_published: boolean;
  updated_at: string;
};

type StorefrontAsset = "logo" | "cover";

function toContent(form: StorefrontContent): StorefrontContent {
  return {
    ...form,
    services: form.services.map((value) => value.trim()).filter(Boolean),
    categories: form.categories.map((value) => value.trim()).filter(Boolean),
  };
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value).sort(([left], [right]) => left.localeCompare(right));
    return `{${entries.map(([key, entry]) => `${JSON.stringify(key)}:${stableStringify(entry)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function useDraftAssetPreview(asset: StorefrontAsset, exists: boolean, updatedAt?: string) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setPreviewUrl(null);
    if (!exists) return;

    void api
      .blob(`core/storefront/assets/${asset}/`, "*/*")
      .then((image) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(image);
        setPreviewUrl(objectUrl);
      })
      .catch((error: Error) => {
        if (!cancelled) {
          toast.error(`Impossible de charger le ${asset === "logo" ? "logo" : "visuel"}.`, {
            description: error.message,
          });
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [asset, exists, updatedAt]);

  return previewUrl;
}

function StorefrontSettingsPage() {
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StorefrontContent | null>(null);
  const [selectedLogo, setSelectedLogo] = useState<File | null>(null);
  const [selectedCover, setSelectedCover] = useState<File | null>(null);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const query = useQuery({
    queryKey: ["tenant-storefront"],
    queryFn: () => api.get<StorefrontSettings>("core/storefront/"),
    enabled: isAdmin,
  });

  useEffect(() => {
    if (query.data && !form) setForm(query.data.draft);
  }, [query.data, form]);

  const savedDraft = query.data?.draft;
  const content = useMemo(() => (form ? toContent(form) : null), [form]);
  const logoPreview = useDraftAssetPreview(
    "logo",
    query.data?.draft_assets.logo ?? false,
    query.data?.updated_at,
  );
  const coverPreview = useDraftAssetPreview(
    "cover",
    query.data?.draft_assets.cover ?? false,
    query.data?.updated_at,
  );
  const hasUnsavedChanges =
    !!content && !!savedDraft && stableStringify(content) !== stableStringify(savedDraft);
  const hasUnpublishedAssetChanges =
    !!query.data &&
    (query.data.draft_assets.logo !== query.data.published_assets.logo ||
      query.data.draft_assets.cover !== query.data.published_assets.cover);
  const hasUnpublishedChanges = hasUnsavedChanges || hasUnpublishedAssetChanges;

  const saveDraft = useMutation({
    mutationFn: (draft: StorefrontContent) =>
      api.patch<StorefrontSettings>("core/storefront/", { draft }),
    onSuccess: (data) => {
      queryClient.setQueryData(["tenant-storefront"], data);
      setForm(data.draft);
      setConfirmPublish(false);
      toast.success("Brouillon de la vitrine enregistré.");
    },
    onError: (error: Error) =>
      toast.error("Impossible d’enregistrer le brouillon.", { description: error.message }),
  });

  const publish = useMutation({
    mutationFn: () => api.post<StorefrontSettings>("core/storefront/publish/", {}),
    onSuccess: (data) => {
      queryClient.setQueryData(["tenant-storefront"], data);
      setForm(data.draft);
      setConfirmPublish(false);
      toast.success("La vitrine a été publiée.");
    },
    onError: (error: Error) =>
      toast.error("Impossible de publier la vitrine.", { description: error.message }),
  });

  const uploadAsset = useMutation({
    mutationFn: async ({ asset, file }: { asset: StorefrontAsset; file: File }) => {
      const body = new FormData();
      body.set("image", file);
      return api.post<StorefrontSettings>(`core/storefront/assets/${asset}/`, body);
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["tenant-storefront"], data);
      if (variables.asset === "logo") setSelectedLogo(null);
      else setSelectedCover(null);
      setConfirmPublish(false);
      toast.success(`${variables.asset === "logo" ? "Logo" : "Couverture"} ajoutée au brouillon.`);
    },
    onError: (error: Error) =>
      toast.error("Impossible d’envoyer cette image.", { description: error.message }),
  });

  const removeAsset = useMutation({
    mutationFn: (asset: StorefrontAsset) =>
      api.delete<StorefrontSettings>(`core/storefront/assets/${asset}/`),
    onSuccess: (data, asset) => {
      if (data) queryClient.setQueryData(["tenant-storefront"], data);
      if (asset === "logo") setSelectedLogo(null);
      else setSelectedCover(null);
      setConfirmPublish(false);
      toast.success("L’image a été retirée du brouillon.");
    },
    onError: (error: Error) =>
      toast.error("Impossible de retirer cette image.", { description: error.message }),
  });

  function update<K extends keyof StorefrontContent>(key: K, value: StorefrontContent[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setConfirmPublish(false);
  }

  if (!isAdmin) {
    return (
      <main className="page-shell">
        <section className="panel p-6">
          <h1 className="font-display text-2xl font-bold">Accès réservé</h1>
          <p className="text-muted-foreground mt-2">
            Seul l’administrateur de l’entreprise peut modifier sa vitrine.
          </p>
        </section>
      </main>
    );
  }

  if (query.isLoading) {
    return (
      <main className="page-shell">
        <p role="status">Chargement de la configuration de la vitrine…</p>
      </main>
    );
  }

  if (query.error || !query.data || !form || !content) {
    return (
      <main className="page-shell">
        <section className="panel space-y-3 p-6">
          <h1 className="font-display text-2xl font-bold">Configuration indisponible</h1>
          <p className="text-muted-foreground">
            {query.error instanceof ApiError
              ? query.error.message
              : "Impossible de charger la vitrine. Vérifiez la connexion au serveur puis réessayez."}
          </p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            Réessayer
          </Button>
        </section>
      </main>
    );
  }

  const storefrontUrl = `${window.location.origin}/entreprise/${query.data.tenant_slug}`;
  const saving =
    saveDraft.isPending || publish.isPending || uploadAsset.isPending || removeAsset.isPending;

  return (
    <main className="page-shell space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-primary text-xs font-semibold uppercase tracking-widest">
            Configuration de l’entreprise
          </p>
          <h1 className="font-display mt-2 text-3xl font-bold">Vitrine publique</h1>
          <p className="text-muted-foreground mt-2 max-w-2xl">
            Modifiez votre présentation sans changer les paramètres globaux de DJIBEXA. Les
            modifications restent privées jusqu’à leur publication.
          </p>
        </div>
        <a
          className="text-primary inline-flex items-center gap-2 text-sm font-medium"
          href={storefrontUrl}
          target="_blank"
          rel="noreferrer"
        >
          Voir la vitrine
          <ExternalLink className="size-4" aria-hidden="true" />
        </a>
      </header>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]">
        <div className="space-y-5">
          <section className="panel space-y-4 p-5">
            <div className="flex items-center gap-2">
              <Globe2 className="text-primary size-5" aria-hidden="true" />
              <h2 className="font-display text-lg font-bold">Identité et présentation</h2>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="storefront-title">Nom commercial</Label>
                <Input
                  id="storefront-title"
                  maxLength={200}
                  value={form.title}
                  onChange={(event) => update("title", event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="storefront-industry">Activité</Label>
                <Input
                  id="storefront-industry"
                  maxLength={120}
                  value={form.industry}
                  onChange={(event) => update("industry", event.target.value)}
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="storefront-tagline">Slogan</Label>
                <Input
                  id="storefront-tagline"
                  maxLength={240}
                  value={form.tagline}
                  onChange={(event) => update("tagline", event.target.value)}
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="storefront-description">Présentation</Label>
                <Textarea
                  id="storefront-description"
                  maxLength={2000}
                  rows={5}
                  value={form.description}
                  onChange={(event) => update("description", event.target.value)}
                />
              </div>
            </div>
          </section>

          <section className="panel space-y-4 p-5">
            <h2 className="font-display text-lg font-bold">Services et catégories</h2>
            <p className="text-muted-foreground text-sm">
              Saisissez un élément par ligne, avec un maximum de 12 services et 20 catégories.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="storefront-services">Services</Label>
                <Textarea
                  id="storefront-services"
                  rows={6}
                  value={form.services.join("\n")}
                  onChange={(event) => update("services", event.target.value.split("\n"))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="storefront-categories">Catégories</Label>
                <Textarea
                  id="storefront-categories"
                  rows={6}
                  value={form.categories.join("\n")}
                  onChange={(event) => update("categories", event.target.value.split("\n"))}
                />
              </div>
            </div>
          </section>

          <section className="panel space-y-4 p-5">
            <h2 className="font-display text-lg font-bold">Logo et image de couverture</h2>
            <p className="text-muted-foreground text-sm">
              PNG, JPEG ou WebP, 5 Mo maximum et jusqu’à 16 millions de pixels. Les changements
              restent privés jusqu’à la publication.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <StorefrontImageControl
                asset="logo"
                exists={query.data.draft_assets.logo}
                previewUrl={logoPreview}
                file={selectedLogo}
                disabled={saving}
                onFileChange={setSelectedLogo}
                onUpload={() => {
                  if (selectedLogo) uploadAsset.mutate({ asset: "logo", file: selectedLogo });
                }}
                onRemove={() => removeAsset.mutate("logo")}
              />
              <StorefrontImageControl
                asset="cover"
                exists={query.data.draft_assets.cover}
                previewUrl={coverPreview}
                file={selectedCover}
                disabled={saving}
                onFileChange={setSelectedCover}
                onUpload={() => {
                  if (selectedCover) uploadAsset.mutate({ asset: "cover", file: selectedCover });
                }}
                onRemove={() => removeAsset.mutate("cover")}
              />
            </div>
          </section>

          <section className="panel space-y-4 p-5">
            <h2 className="font-display text-lg font-bold">Coordonnées</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="storefront-phone">Téléphone</Label>
                <Input
                  id="storefront-phone"
                  maxLength={30}
                  value={form.phone}
                  onChange={(event) => update("phone", event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="storefront-email">Courriel</Label>
                <Input
                  id="storefront-email"
                  type="email"
                  value={form.email}
                  onChange={(event) => update("email", event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="storefront-address">Adresse</Label>
                <Input
                  id="storefront-address"
                  maxLength={240}
                  value={form.address}
                  onChange={(event) => update("address", event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="storefront-city">Ville</Label>
                <Input
                  id="storefront-city"
                  maxLength={120}
                  value={form.city}
                  onChange={(event) => update("city", event.target.value)}
                />
              </div>
            </div>
          </section>

          <section className="panel space-y-4 p-5">
            <h2 className="font-display text-lg font-bold">Apparence et sections visibles</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <ColorInput
                id="storefront-primary"
                label="Couleur principale"
                value={form.primary_color}
                onChange={(value) => update("primary_color", value)}
              />
              <ColorInput
                id="storefront-accent"
                label="Couleur d’accent"
                value={form.accent_color}
                onChange={(value) => update("accent_color", value)}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <SectionSwitch
                id="storefront-about"
                label="Présentation"
                checked={form.sections.about}
                onCheckedChange={(checked) =>
                  update("sections", { ...form.sections, about: checked })
                }
              />
              <SectionSwitch
                id="storefront-services-visible"
                label="Services"
                checked={form.sections.services}
                onCheckedChange={(checked) =>
                  update("sections", { ...form.sections, services: checked })
                }
              />
              <SectionSwitch
                id="storefront-categories-visible"
                label="Catégories"
                checked={form.sections.categories}
                onCheckedChange={(checked) =>
                  update("sections", { ...form.sections, categories: checked })
                }
              />
              <SectionSwitch
                id="storefront-contact-visible"
                label="Coordonnées"
                checked={form.sections.contact}
                onCheckedChange={(checked) =>
                  update("sections", { ...form.sections, contact: checked })
                }
              />
            </div>
          </section>

          <section className="panel flex flex-wrap items-center justify-between gap-3 p-5">
            <p className="text-muted-foreground text-sm">
              {hasUnsavedChanges
                ? "Enregistrez le brouillon avant de le publier."
                : hasUnpublishedChanges
                  ? "Des changements du brouillon ne sont pas encore publiés."
                  : query.data.is_published
                    ? `Dernière publication : ${new Date(query.data.published_at ?? "").toLocaleString()}`
                    : "Cette vitrine n’est pas encore publiée."}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={saving || !hasUnsavedChanges}
                onClick={() => saveDraft.mutate(content)}
              >
                <Save className="mr-2 size-4" aria-hidden="true" />
                Enregistrer le brouillon
              </Button>
              <Button
                variant={confirmPublish ? "destructive" : "default"}
                disabled={
                  saving || hasUnsavedChanges || (query.data.is_published && !hasUnpublishedChanges)
                }
                onClick={() => {
                  if (confirmPublish) publish.mutate();
                  else setConfirmPublish(true);
                }}
              >
                {confirmPublish ? "Confirmer la publication" : "Publier la vitrine"}
              </Button>
              {confirmPublish && (
                <Button variant="ghost" disabled={saving} onClick={() => setConfirmPublish(false)}>
                  Annuler
                </Button>
              )}
            </div>
          </section>
        </div>

        <aside className="panel space-y-4 p-5 xl:sticky xl:top-6">
          <div className="flex items-center gap-2">
            <Eye className="text-primary size-5" aria-hidden="true" />
            <h2 className="font-display text-lg font-bold">Aperçu du brouillon</h2>
          </div>
          <p className="text-muted-foreground text-sm">
            Cet aperçu n’est visible que par vous. Enregistrez puis publiez pour le rendre public.
          </p>
          <div className="overflow-hidden rounded-xl border">
            <div
              className="space-y-2 bg-cover bg-center p-5 text-white"
              style={{
                backgroundImage: coverPreview
                  ? `linear-gradient(135deg, ${content.primary_color}dd, ${content.accent_color}cc), url("${coverPreview}")`
                  : `linear-gradient(135deg, ${content.primary_color}, ${content.accent_color})`,
              }}
            >
              {logoPreview && (
                <img src={logoPreview} alt="" className="h-12 max-w-32 object-contain" />
              )}
              {content.industry && (
                <p className="text-xs uppercase tracking-widest">{content.industry}</p>
              )}
              <h3 className="text-2xl font-bold">{content.title || "Nom de l’entreprise"}</h3>
              {content.tagline && <p>{content.tagline}</p>}
            </div>
            <div className="space-y-3 p-5">
              {content.sections.about && content.description && (
                <div>
                  <p className="text-sm font-semibold">Présentation</p>
                  <p className="text-muted-foreground mt-1 text-sm">{content.description}</p>
                </div>
              )}
              {content.sections.services && content.services.length > 0 && (
                <div>
                  <p className="text-sm font-semibold">Services</p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {content.services.join(" · ")}
                  </p>
                </div>
              )}
              {content.sections.categories && content.categories.length > 0 && (
                <div>
                  <p className="text-sm font-semibold">Catégories</p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {content.categories.join(" · ")}
                  </p>
                </div>
              )}
              {content.sections.contact && (content.phone || content.email || content.city) && (
                <div>
                  <p className="text-sm font-semibold">Contact</p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {[content.phone, content.email, content.city].filter(Boolean).join(" · ")}
                  </p>
                </div>
              )}
            </div>
          </div>
          <p className="text-muted-foreground break-all text-xs">
            Adresse publique actuelle : {storefrontUrl}
          </p>
          <p className="text-muted-foreground text-xs">
            Aucun domaine personnalisé n’est configuré depuis cet écran.
          </p>
        </aside>
      </div>
    </main>
  );
}

function ColorInput({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-3">
        <Input
          id={id}
          type="color"
          value={/^#[\da-f]{6}$/i.test(value) ? value : "#123D60"}
          onChange={(event) => onChange(event.target.value)}
          className="h-10 w-16 p-1"
        />
        <span className="text-muted-foreground text-sm">{value}</span>
      </div>
    </div>
  );
}

function StorefrontImageControl({
  asset,
  exists,
  previewUrl,
  file,
  disabled,
  onFileChange,
  onUpload,
  onRemove,
}: {
  asset: StorefrontAsset;
  exists: boolean;
  previewUrl: string | null;
  file: File | null;
  disabled: boolean;
  onFileChange: (file: File | null) => void;
  onUpload: () => void;
  onRemove: () => void;
}) {
  const label = asset === "logo" ? "Logo" : "Image de couverture";
  const inputId = `storefront-${asset}-file`;

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <Label htmlFor={inputId}>{label}</Label>
      {previewUrl ? (
        <div className="bg-muted/30 flex h-24 items-center justify-center rounded-md p-2">
          <img
            src={previewUrl}
            alt={`Aperçu du ${asset === "logo" ? "logo" : "visuel de couverture"}`}
            className={
              asset === "logo"
                ? "max-h-full max-w-full object-contain"
                : "h-full w-full object-cover"
            }
          />
        </div>
      ) : (
        <p className="text-muted-foreground flex h-24 items-center justify-center rounded-md border border-dashed text-sm">
          Aucune image dans le brouillon
        </p>
      )}
      <Input
        id={inputId}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={disabled}
        onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
      />
      {file && <p className="text-muted-foreground truncate text-xs">{file.name}</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={disabled || !file} onClick={onUpload}>
          Envoyer
        </Button>
        {exists && (
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={onRemove}>
            Retirer du brouillon
          </Button>
        )}
      </div>
    </div>
  );
}

function SectionSwitch({
  id,
  label,
  checked,
  onCheckedChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
      <Label htmlFor={id}>{label}</Label>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
