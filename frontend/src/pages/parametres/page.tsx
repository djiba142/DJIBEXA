import { createFileRoute } from "@tanstack/react-router";
import { Download, Plus, RotateCcw, Save, Trash2, Upload } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DEFAULT_SETTINGS, loadSettings, saveSettings, type AppSettings } from "@/lib/settings";
import { useLocale, type Language } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/parametres")({
  head: () => ({
    meta: [
      { title: "Paramètres — ERP DJIBEXA" },
      {
        name: "description",
        content: "Configuration complète de l'entreprise, des documents et du stock.",
      },
      { property: "og:title", content: "Paramètres — ERP DJIBEXA" },
      { property: "og:description", content: "Configuration de l'ERP DJIBEXA." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: SettingsPage,
});

type ExchangeRateRow = {
  id: number;
  source_currency: string;
  target_currency: string;
  rate: string;
  effective_date: string;
  created_by_name: string;
  created_at: string;
};

function localDateInputValue() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel space-y-4 p-5">
      <h2 className="font-display text-lg font-bold uppercase tracking-wide">{title}</h2>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function SignatureDrawingPad({
  onSave,
  disabled,
}: {
  onSave: (file: File) => Promise<void>;
  disabled: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);
  const [hasInk, setHasInk] = useState(false);

  function getPoint(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const bounds = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * canvas.width,
      y: ((event.clientY - bounds.top) / bounds.height) * canvas.height,
    };
  }

  function startDrawing(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const point = getPoint(event);
    const context = canvas?.getContext("2d");
    if (!canvas || !point || !context) return;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    context.beginPath();
    context.moveTo(point.x, point.y);
    context.lineWidth = 5;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#123D60";
    drawingRef.current = true;
    setHasInk(true);
  }

  function continueDrawing(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const point = getPoint(event);
    const context = canvasRef.current?.getContext("2d");
    if (!point || !context) return;
    event.preventDefault();
    context.lineTo(point.x, point.y);
    context.stroke();
  }

  function clearDrawing() {
    const canvas = canvasRef.current;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    setHasInk(false);
  }

  function saveDrawing() {
    const canvas = canvasRef.current;
    if (!canvas || !hasInk || disabled) return;
    canvas.toBlob((blob) => {
      if (!blob) {
        toast.error("Impossible de convertir le dessin en image.");
        return;
      }
      void onSave(new File([blob], "signature-vendeur.png", { type: "image/png" }));
    }, "image/png");
  }

  return (
    <div className="space-y-2">
      <div className="rounded border bg-white p-2">
        <canvas
          ref={canvasRef}
          width={800}
          height={200}
          aria-label="Zone de dessin de la signature du vendeur"
          className="h-32 w-full touch-none cursor-crosshair sm:h-40"
          onPointerDown={startDrawing}
          onPointerMove={continueDrawing}
          onPointerUp={() => {
            drawingRef.current = false;
          }}
          onPointerCancel={() => {
            drawingRef.current = false;
          }}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={clearDrawing}
          disabled={disabled || !hasInk}
        >
          Effacer le dessin
        </Button>
        <Button type="button" onClick={saveDrawing} disabled={disabled || !hasInk}>
          Enregistrer la signature dessinée
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        Dessinez avec la souris, un stylet ou le doigt. Le tracé enregistré sera utilisé sur les
        prochaines factures.
      </p>
    </div>
  );
}

function SettingsPage() {
  const { language, changeLanguage, t } = useLocale();
  const { hasRole } = useAuth();
  const isAdmin = hasRole("admin");
  const queryClient = useQueryClient();
  const [s, setS] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [rateForm, setRateForm] = useState({ rate: "", effective_date: localDateInputValue() });
  const [creditReminders, setCreditReminders] = useState({
    enabled: true,
    frequency: "weekly" as const,
    day_of_week: 4,
    time: "17:00",
    timezone: "Africa/Conakry",
  });
  const [saving, setSaving] = useState(false);
  const [uploadingAsset, setUploadingAsset] = useState<string | null>(null);
  const [signatureEditorOpen, setSignatureEditorOpen] = useState(false);
  const { data: exchangeRates } = useQuery({
    queryKey: ["exchange-rates"],
    queryFn: () =>
      api.list<ExchangeRateRow>("suppliers/exchange-rates/", {
        source_currency: "USD",
        target_currency: "GNF",
      }),
    enabled: isAdmin,
  });
  const saveExchangeRate = useMutation({
    mutationFn: () =>
      api.post<ExchangeRateRow>("suppliers/exchange-rates/", {
        source_currency: "USD",
        target_currency: "GNF",
        rate: rateForm.rate,
        effective_date: rateForm.effective_date,
      }),
    onSuccess: () => {
      setRateForm({ rate: "", effective_date: localDateInputValue() });
      void queryClient.invalidateQueries({ queryKey: ["exchange-rates"] });
      toast.success(t("settings.exchangeRateSaved"));
    },
    onError: (error: Error) =>
      toast.error(t("settings.exchangeRateSaveError"), { description: error.message }),
  });
  useEffect(() => {
    setS({ ...loadSettings(), currency: "GNF" });
    api
      .get<{
        company_name: string;
        activity: string;
        distributor_details: string;
        address: string;
        phone_numbers: string[];
        email: string;
        email_addresses: string[];
        additional_lines: string[];
        line_display_mode: "compact" | "carnet";
        header_alignment: "left" | "center";
        header_color: string;
        text_color: string;
        show_company_name: boolean;
        show_activity: boolean;
        show_distributor: boolean;
        show_address: boolean;
        show_phones: boolean;
        show_emails: boolean;
        show_rccm: boolean;
        show_nif: boolean;
        show_logo: boolean;
        show_automotive_image: boolean;
        show_watermark: boolean;
        show_stamp: boolean;
        show_qr: boolean;
        logo_url: string;
        automotive_image_url: string;
        watermark_image_url: string;
        stamp_image_url: string;
        stamp_position: "left" | "center" | "right";
        stamp_size_mm: number;
        stamp_opacity: number;
        show_seller_signature: boolean;
        seller_signature_name: string;
        seller_signature_title: string;
        seller_signature_image_url: string;
        rccm: string;
        nif: string;
      }>("invoices/branding/")
      .then((branding) =>
        setS((current) => ({
          ...current,
          companyName: branding.company_name,
          slogan: branding.activity,
          distributorDetails: branding.distributor_details,
          address: branding.address,
          phoneNumbers: branding.phone_numbers,
          phone: branding.phone_numbers.join(" / "),
          email: branding.email,
          emailAddresses: branding.email_addresses ?? (branding.email ? [branding.email] : []),
          additionalInvoiceLines: branding.additional_lines ?? [],
          invoiceLineDisplayMode: branding.line_display_mode,
          invoiceHeaderAlignment: branding.header_alignment,
          invoiceHeaderColor: branding.header_color,
          invoiceTextColor: branding.text_color,
          invoiceShowCompanyName: branding.show_company_name,
          invoiceShowActivity: branding.show_activity,
          invoiceShowDistributor: branding.show_distributor,
          invoiceShowAddress: branding.show_address,
          invoiceShowPhones: branding.show_phones,
          invoiceShowEmails: branding.show_emails,
          invoiceShowRccm: branding.show_rccm,
          invoiceShowNif: branding.show_nif,
          invoiceShowLogo: branding.show_logo,
          invoiceShowAutomotiveImage: branding.show_automotive_image,
          invoiceShowWatermark: branding.show_watermark,
          invoiceShowStamp: branding.show_stamp,
          invoiceShowQr: branding.show_qr,
          invoiceLogoUrl: branding.logo_url,
          invoiceAutomotiveImageUrl: branding.automotive_image_url,
          invoiceWatermarkUrl: branding.watermark_image_url,
          invoiceStampImageUrl: branding.stamp_image_url,
          invoiceStampPosition: branding.stamp_position,
          invoiceStampSizeMm: branding.stamp_size_mm,
          invoiceStampOpacity: branding.stamp_opacity,
          invoiceShowSellerSignature: branding.show_seller_signature,
          invoiceSellerSignatureName: branding.seller_signature_name,
          invoiceSellerSignatureTitle: branding.seller_signature_title,
          invoiceSellerSignatureUrl: branding.seller_signature_image_url,
          rccm: branding.rccm,
          nif: branding.nif,
        })),
      )
      .catch((error: unknown) =>
        toast.error(error instanceof Error ? error.message : t("settings.loadError")),
      );
    api
      .get<typeof creditReminders>("notifications/reminders/settings/")
      .then(setCreditReminders)
      .catch((error: unknown) =>
        toast.error(error instanceof Error ? error.message : t("settings.reminderLoadError")),
      );
  }, [t]);
  const set = <K extends keyof AppSettings>(k: K, v: AppSettings[K]) =>
    setS((p) => ({ ...p, [k]: v }));

  async function saveBrandingImage(
    field:
      | "logo_image"
      | "automotive_image"
      | "watermark_image"
      | "stamp_image"
      | "seller_signature_image",
    stateKey:
      | "invoiceLogoUrl"
      | "invoiceAutomotiveImageUrl"
      | "invoiceWatermarkUrl"
      | "invoiceStampImageUrl"
      | "invoiceSellerSignatureUrl",
    file: File | null,
  ) {
    setUploadingAsset(field);
    try {
      const urlKey = {
        logo_image: "logo_url",
        automotive_image: "automotive_image_url",
        watermark_image: "watermark_image_url",
        stamp_image: "stamp_image_url",
        seller_signature_image: "seller_signature_image_url",
      }[field] as
        | "logo_url"
        | "automotive_image_url"
        | "watermark_image_url"
        | "stamp_image_url"
        | "seller_signature_image_url";
      let result: Record<string, string>;
      if (file) {
        const formData = new FormData();
        formData.append(field, file);
        if (field === "seller_signature_image") {
          formData.append("seller_signature_name", s.invoiceSellerSignatureName);
          formData.append("seller_signature_title", s.invoiceSellerSignatureTitle);
          formData.append("show_seller_signature", String(s.invoiceShowSellerSignature));
        }
        result = await api.patch<Record<string, string>>("invoices/branding/", formData);
      } else {
        const asset =
          field === "seller_signature_image" ? "signature" : field.replace("_image", "");
        await api.delete(`invoices/branding/assets/${asset}/`);
        result = await api.get<Record<string, string>>("invoices/branding/");
      }
      set(stateKey, result[urlKey] ?? "");
      toast.success(file ? "Image enregistrée" : "Image supprimée");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Enregistrement de l’image impossible.");
    } finally {
      setUploadingAsset(null);
    }
  }

  const text = (k: keyof AppSettings, label: string, type = "text") => (
    <div className="space-y-1.5">
      <Label htmlFor={k}>{label}</Label>
      <Input
        id={k}
        type={type}
        value={String(s[k])}
        onChange={(e) =>
          set(k, (type === "number" ? Number(e.target.value) : e.target.value) as never)
        }
      />
    </div>
  );

  const repeatableInputs = (
    id: string,
    label: string,
    values: string[],
    onChange: (nextValues: string[]) => void,
    type = "text",
  ) => {
    const rows = values.length ? values : [""];
    return (
      <div className="space-y-2 sm:col-span-2">
        <Label>{label}</Label>
        {rows.map((value, index) => (
          <div key={`${id}-${index}`} className="flex min-w-0 gap-2">
            <Input
              aria-label={`${label} ${index + 1}`}
              type={type}
              value={value}
              onChange={(event) =>
                onChange(
                  rows.map((current, rowIndex) =>
                    rowIndex === index ? event.target.value : current,
                  ),
                )
              }
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Supprimer ${label.toLowerCase()} ${index + 1}`}
              title={`Supprimer ${label.toLowerCase()}`}
              onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...rows, ""])}>
          <Plus className="size-4" /> Ajouter {label.toLowerCase()}
        </Button>
      </div>
    );
  };

  const visibilityControl = (
    label: string,
    checked: boolean,
    onChange: (value: boolean) => void,
  ) => (
    <label className="flex items-center justify-between gap-3 rounded border p-3">
      <span className="text-sm">{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  );

  const imageControl = (
    field:
      | "logo_image"
      | "automotive_image"
      | "watermark_image"
      | "stamp_image"
      | "seller_signature_image",
    title: string,
    imageUrl: string,
    stateKey:
      | "invoiceLogoUrl"
      | "invoiceAutomotiveImageUrl"
      | "invoiceWatermarkUrl"
      | "invoiceStampImageUrl"
      | "invoiceSellerSignatureUrl",
  ) => (
    <div className="space-y-2 rounded border p-3">
      <Label htmlFor={field}>{title}</Label>
      <Input
        id={field}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={uploadingAsset === field}
        onChange={(event) => {
          const file = event.target.files?.[0] ?? null;
          if (file) void saveBrandingImage(field, stateKey, file);
          event.currentTarget.value = "";
        }}
      />
      <div className="flex items-center justify-between gap-3">
        {imageUrl ? (
          <img src={imageUrl} alt={title} className="h-16 max-w-40 object-contain" />
        ) : (
          <span className="text-muted-foreground text-xs">Aucune image configurée</span>
        )}
        {imageUrl && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Supprimer ${title.toLowerCase()}`}
            onClick={() => void saveBrandingImage(field, stateKey, null)}
            disabled={uploadingAsset === field}
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold uppercase">{t("settings.title")}</h1>
          <p className="text-muted-foreground text-sm">{t("settings.subtitle")}</p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <Button
            variant="outline"
            className="w-full sm:w-auto"
            onClick={() => {
              setS(DEFAULT_SETTINGS);
              setCreditReminders((current) => ({
                ...current,
                enabled: true,
                frequency: "weekly",
                day_of_week: 4,
                time: "17:00",
              }));
            }}
          >
            <RotateCcw className="size-4" /> {t("settings.defaults")}
          </Button>
          <Button
            className="w-full sm:w-auto"
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              try {
                const saveRequests = [
                  api.patch("notifications/reminders/settings/", {
                    enabled: creditReminders.enabled,
                    frequency: creditReminders.frequency,
                    day_of_week: creditReminders.day_of_week,
                    time: creditReminders.time,
                  }),
                ];
                if (isAdmin) {
                  saveRequests.push(
                    api.patch("invoices/branding/", {
                      company_name: s.companyName,
                      activity: s.slogan,
                      distributor_details: s.distributorDetails,
                      address: s.address,
                      phone_numbers: s.phoneNumbers.map((phone) => phone.trim()).filter(Boolean),
                      email_addresses: s.emailAddresses
                        .map((email) => email.trim())
                        .filter(Boolean),
                      additional_lines: s.additionalInvoiceLines
                        .map((line) => line.trim())
                        .filter(Boolean),
                      line_display_mode: s.invoiceLineDisplayMode,
                      header_alignment: s.invoiceHeaderAlignment,
                      header_color: s.invoiceHeaderColor,
                      text_color: s.invoiceTextColor,
                      show_company_name: s.invoiceShowCompanyName,
                      show_activity: s.invoiceShowActivity,
                      show_distributor: s.invoiceShowDistributor,
                      show_address: s.invoiceShowAddress,
                      show_phones: s.invoiceShowPhones,
                      show_emails: s.invoiceShowEmails,
                      show_rccm: s.invoiceShowRccm,
                      show_nif: s.invoiceShowNif,
                      show_logo: s.invoiceShowLogo,
                      show_automotive_image: s.invoiceShowAutomotiveImage,
                      show_watermark: s.invoiceShowWatermark,
                      show_stamp: s.invoiceShowStamp,
                      show_qr: s.invoiceShowQr,
                      stamp_position: s.invoiceStampPosition,
                      stamp_size_mm: s.invoiceStampSizeMm,
                      stamp_opacity: s.invoiceStampOpacity,
                      show_seller_signature: s.invoiceShowSellerSignature,
                      seller_signature_name: s.invoiceSellerSignatureName,
                      seller_signature_title: s.invoiceSellerSignatureTitle,
                      rccm: s.rccm,
                      nif: s.nif,
                    }),
                  );
                }
                await Promise.all(saveRequests);
                saveSettings({ ...s, currency: "GNF" });
                toast.success(t("settings.saved"));
              } catch (error) {
                toast.error(error instanceof Error ? error.message : t("settings.saveError"));
              } finally {
                setSaving(false);
              }
            }}
          >
            <Save className="size-4" /> {t("common.save")}
          </Button>
        </div>
      </div>

      {isAdmin && (
        <Section title="Facturation · En-tête de facture">
          {text("companyName", t("settings.companyName"))}
          {text("slogan", t("settings.slogan"))}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="distributorDetails">Distributeur agréé / détails</Label>
            <Textarea
              id="distributorDetails"
              value={s.distributorDetails}
              onChange={(event) => set("distributorDetails", event.target.value)}
            />
          </div>
          {text("address", t("settings.address"))}
          {repeatableInputs("invoice-phone", "Téléphones", s.phoneNumbers, (phoneNumbers) => {
            set("phoneNumbers", phoneNumbers);
            set("phone", phoneNumbers.join(" / "));
          })}
          {text("whatsapp", "WhatsApp")}
          {repeatableInputs(
            "invoice-email",
            "Adresses e-mail",
            s.emailAddresses,
            (emailAddresses) => {
              set("emailAddresses", emailAddresses);
              set("email", emailAddresses[0] ?? "");
            },
            "email",
          )}
          {repeatableInputs(
            "invoice-extra-line",
            "Autres informations à imprimer",
            s.additionalInvoiceLines,
            (additionalInvoiceLines) => set("additionalInvoiceLines", additionalInvoiceLines),
          )}
          {text("rccm", t("settings.rccm"))}
          {text("nif", t("settings.nif"))}
          <div className="space-y-1.5">
            <Label htmlFor="invoiceHeaderColor">Couleur du bandeau</Label>
            <Input
              id="invoiceHeaderColor"
              type="color"
              value={s.invoiceHeaderColor}
              onChange={(event) => set("invoiceHeaderColor", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="invoiceTextColor">Couleur du texte</Label>
            <Input
              id="invoiceTextColor"
              type="color"
              value={s.invoiceTextColor}
              onChange={(event) => set("invoiceTextColor", event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="invoiceLineDisplayMode">Lignes du tableau</Label>
            <Select
              value={s.invoiceLineDisplayMode}
              onValueChange={(value) =>
                set("invoiceLineDisplayMode", value as "compact" | "carnet")
              }
            >
              <SelectTrigger id="invoiceLineDisplayMode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="compact">Compact : produits saisis seulement</SelectItem>
                <SelectItem value="carnet">Carnet : compléter à 25 lignes</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {visibilityControl("Nom commercial", s.invoiceShowCompanyName, (value) =>
            set("invoiceShowCompanyName", value),
          )}
          {visibilityControl("Activité", s.invoiceShowActivity, (value) =>
            set("invoiceShowActivity", value),
          )}
          {visibilityControl("Distributeur", s.invoiceShowDistributor, (value) =>
            set("invoiceShowDistributor", value),
          )}
          {visibilityControl("Adresse", s.invoiceShowAddress, (value) =>
            set("invoiceShowAddress", value),
          )}
          {visibilityControl("Téléphones", s.invoiceShowPhones, (value) =>
            set("invoiceShowPhones", value),
          )}
          {visibilityControl("E-mails", s.invoiceShowEmails, (value) =>
            set("invoiceShowEmails", value),
          )}
          {visibilityControl("RCCM", s.invoiceShowRccm, (value) => set("invoiceShowRccm", value))}
          {visibilityControl("NIF", s.invoiceShowNif, (value) => set("invoiceShowNif", value))}
          {visibilityControl("Logo", s.invoiceShowLogo, (value) => set("invoiceShowLogo", value))}
          {visibilityControl("Illustration automobile", s.invoiceShowAutomotiveImage, (value) =>
            set("invoiceShowAutomotiveImage", value),
          )}
          {visibilityControl("Filigrane", s.invoiceShowWatermark, (value) =>
            set("invoiceShowWatermark", value),
          )}
          {visibilityControl("Cachet", s.invoiceShowStamp, (value) =>
            set("invoiceShowStamp", value),
          )}
          {visibilityControl("QR de vérification", s.invoiceShowQr, (value) =>
            set("invoiceShowQr", value),
          )}
          {imageControl("logo_image", "Logo de l’entreprise", s.invoiceLogoUrl, "invoiceLogoUrl")}
          {imageControl(
            "automotive_image",
            "Illustration automobile",
            s.invoiceAutomotiveImageUrl,
            "invoiceAutomotiveImageUrl",
          )}
          {imageControl(
            "watermark_image",
            "Image du filigrane",
            s.invoiceWatermarkUrl,
            "invoiceWatermarkUrl",
          )}
          {imageControl(
            "stamp_image",
            "Cachet officiel (PNG, JPG ou WebP)",
            s.invoiceStampImageUrl,
            "invoiceStampImageUrl",
          )}
          <div className="space-y-3 rounded border p-3 sm:col-span-2">
            <h3 className="text-sm font-semibold">Configuration du cachet sur la facture</h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="invoiceStampPosition">Position dans la zone réservée</Label>
                <Select
                  value={s.invoiceStampPosition}
                  onValueChange={(value) =>
                    set("invoiceStampPosition", value as "left" | "center" | "right")
                  }
                >
                  <SelectTrigger id="invoiceStampPosition">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="left">Gauche</SelectItem>
                    <SelectItem value="center">Centre</SelectItem>
                    <SelectItem value="right">Droite</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invoiceStampSize">Taille : {s.invoiceStampSizeMm} mm</Label>
                <Input
                  id="invoiceStampSize"
                  type="range"
                  min={12}
                  max={26}
                  step={1}
                  value={s.invoiceStampSizeMm}
                  onChange={(event) => set("invoiceStampSizeMm", Number(event.target.value))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invoiceStampOpacity">
                  Transparence : {100 - s.invoiceStampOpacity}%
                </Label>
                <Input
                  id="invoiceStampOpacity"
                  type="range"
                  min={20}
                  max={100}
                  step={5}
                  value={s.invoiceStampOpacity}
                  onChange={(event) => set("invoiceStampOpacity", Number(event.target.value))}
                />
              </div>
            </div>
            <div
              aria-label="Aperçu du cachet sur la facture"
              className="flex h-24 items-center rounded border border-dashed bg-white px-6"
              style={{
                justifyContent:
                  s.invoiceStampPosition === "left"
                    ? "flex-start"
                    : s.invoiceStampPosition === "right"
                      ? "flex-end"
                      : "center",
              }}
            >
              {s.invoiceShowStamp &&
                (s.invoiceStampImageUrl ? (
                  <img
                    src={s.invoiceStampImageUrl}
                    alt="Aperçu du cachet officiel"
                    className="aspect-square object-contain"
                    style={{
                      width: `${s.invoiceStampSizeMm * 2.5}px`,
                      height: `${s.invoiceStampSizeMm * 2.5}px`,
                      opacity: s.invoiceStampOpacity / 100,
                    }}
                  />
                ) : (
                  <div
                    className="flex aspect-square flex-col items-center justify-center rounded-full border-[3px] border-double p-1 text-center"
                    style={{
                      width: `${s.invoiceStampSizeMm * 2.5}px`,
                      height: `${s.invoiceStampSizeMm * 2.5}px`,
                      opacity: s.invoiceStampOpacity / 100,
                      borderColor: s.invoiceHeaderColor,
                      color: s.invoiceHeaderColor,
                    }}
                  >
                    <span className="line-clamp-2 max-w-full text-[6px] leading-tight font-bold uppercase">
                      {s.companyName}
                    </span>
                    <span
                      className="my-0.5 w-full truncate px-0.5 py-0.5 text-[7px] leading-none font-black tracking-wide text-white uppercase"
                      style={{ backgroundColor: s.invoiceHeaderColor }}
                    >
                      Validée
                    </span>
                    <span className="text-[5px] leading-none font-bold tracking-widest uppercase">
                      Facture
                    </span>
                  </div>
                ))}
            </div>
            <p className="text-muted-foreground text-xs">
              Si aucune image n’est importée, un cachet rond est généré à partir du nom de
              l’entreprise. La signature cryptographique reste indépendante du cachet visuel.
            </p>
          </div>
          <div className="space-y-3 rounded border p-3 sm:col-span-2">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Signature du vendeur</h3>
                <p className="text-muted-foreground text-xs">
                  La signature dessinée apparaîtra dans la zone dédiée, séparée du cachet et du QR.
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                aria-expanded={signatureEditorOpen}
                onClick={() => setSignatureEditorOpen((open) => !open)}
              >
                {signatureEditorOpen ? "Fermer la configuration" : "Configurer la signature"}
              </Button>
            </div>
            {signatureEditorOpen && (
              <div className="space-y-4">
                {visibilityControl(
                  "Afficher la signature du vendeur sur les prochaines factures",
                  s.invoiceShowSellerSignature,
                  (value) => set("invoiceShowSellerSignature", value),
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="invoiceSellerSignatureName">Nom à afficher</Label>
                    <Input
                      id="invoiceSellerSignatureName"
                      value={s.invoiceSellerSignatureName}
                      maxLength={200}
                      onChange={(event) => set("invoiceSellerSignatureName", event.target.value)}
                      placeholder="Nom du responsable ou du vendeur"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="invoiceSellerSignatureTitle">Fonction (facultatif)</Label>
                    <Input
                      id="invoiceSellerSignatureTitle"
                      value={s.invoiceSellerSignatureTitle}
                      maxLength={100}
                      onChange={(event) => set("invoiceSellerSignatureTitle", event.target.value)}
                      placeholder="Ex. Responsable des ventes"
                    />
                  </div>
                </div>
                {imageControl(
                  "seller_signature_image",
                  "Importer une signature (PNG, JPG ou WebP)",
                  s.invoiceSellerSignatureUrl,
                  "invoiceSellerSignatureUrl",
                )}
                <div className="space-y-2">
                  <Label>Dessiner la signature</Label>
                  <SignatureDrawingPad
                    disabled={uploadingAsset === "seller_signature_image"}
                    onSave={(file) =>
                      saveBrandingImage("seller_signature_image", "invoiceSellerSignatureUrl", file)
                    }
                  />
                </div>
              </div>
            )}
            <div
              className="grid grid-cols-2 gap-2 sm:grid-cols-4"
              aria-label="Aperçu de la zone de signatures"
            >
              <div className="flex min-h-24 flex-col rounded border p-2 text-xs text-blue-900">
                <strong>Signature du client</strong>
                <span className="mt-1">Nom et signature</span>
                <span className="mt-auto border-b border-dotted" />
              </div>
              <div className="flex min-h-24 flex-col rounded border p-2 text-xs text-blue-900">
                <strong>Signature du vendeur</strong>
                <span className="mt-1 truncate">
                  {s.invoiceSellerSignatureName || "Nom du vendeur"}
                </span>
                {s.invoiceShowSellerSignature && s.invoiceSellerSignatureUrl ? (
                  <img
                    src={s.invoiceSellerSignatureUrl}
                    alt="Aperçu de la signature du vendeur"
                    className="mt-auto h-10 w-full object-contain"
                  />
                ) : (
                  <span className="mt-auto border-b border-dotted" />
                )}
              </div>
              <div className="flex min-h-24 flex-col rounded border p-2 text-xs text-blue-900">
                <strong>Validation et cachet</strong>
                {s.invoiceShowStamp && (
                  <div
                    className="flex flex-1 items-center px-1"
                    style={{
                      justifyContent:
                        s.invoiceStampPosition === "left"
                          ? "flex-start"
                          : s.invoiceStampPosition === "right"
                            ? "flex-end"
                            : "center",
                    }}
                  >
                    {s.invoiceStampImageUrl ? (
                      <img
                        src={s.invoiceStampImageUrl}
                        alt="Cachet dans la zone de validation"
                        className="aspect-square object-contain"
                        style={{
                          width: `${Math.min(s.invoiceStampSizeMm * 2.1, 56)}px`,
                          opacity: s.invoiceStampOpacity / 100,
                        }}
                      />
                    ) : (
                      <div
                        className="flex aspect-square flex-col items-center justify-center rounded-full border-[3px] border-double p-1 text-center"
                        style={{
                          width: `${Math.min(s.invoiceStampSizeMm * 2.1, 56)}px`,
                          opacity: s.invoiceStampOpacity / 100,
                          borderColor: s.invoiceHeaderColor,
                          color: s.invoiceHeaderColor,
                        }}
                      >
                        <span className="line-clamp-2 max-w-full text-[5px] leading-tight font-bold uppercase">
                          {s.companyName}
                        </span>
                        <span
                          className="my-0.5 w-full truncate px-0.5 py-0.5 text-[6px] leading-none font-black tracking-wide text-white uppercase"
                          style={{ backgroundColor: s.invoiceHeaderColor }}
                        >
                          Validée
                        </span>
                        <span className="text-[4px] leading-none font-bold tracking-widest uppercase">
                          Facture
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="flex min-h-24 items-center justify-center rounded border p-2 text-center text-xs text-blue-900">
                QR de vérification
              </div>
            </div>
          </div>
          <div className="overflow-hidden rounded border sm:col-span-2">
            <div
              className="flex min-h-28 items-center gap-2 px-4 py-3"
              style={{ backgroundColor: s.invoiceHeaderColor, color: s.invoiceTextColor }}
            >
              {s.invoiceShowLogo && s.invoiceLogoUrl && (
                <img
                  src={s.invoiceLogoUrl}
                  alt="Logo facture"
                  className="max-h-16 w-[13%] shrink-0 object-contain"
                />
              )}
              <div className="min-w-0 flex-1 space-y-0.5 text-center">
                {s.invoiceShowCompanyName && (
                  <p className="truncate text-sm font-bold uppercase">{s.companyName}</p>
                )}
                {s.invoiceShowActivity && <p className="truncate text-[10px]">{s.slogan}</p>}
                {s.invoiceShowDistributor && (
                  <p className="line-clamp-2 text-[10px]">{s.distributorDetails}</p>
                )}
                {s.invoiceShowAddress && <p className="truncate text-[10px]">{s.address}</p>}
                {s.invoiceShowPhones && s.phoneNumbers.length > 0 && (
                  <p className="truncate text-[10px]">Tél. {s.phoneNumbers.join(" · ")}</p>
                )}
                {s.invoiceShowEmails && s.emailAddresses.length > 0 && (
                  <p className="truncate text-[10px]">{s.emailAddresses.join(" · ")}</p>
                )}
                {s.invoiceShowLegalIdentifiers && (
                  <p className="truncate text-[10px]">
                    {[s.rccm && `RCCM ${s.rccm}`, s.nif && `NIF ${s.nif}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                )}
                {s.additionalInvoiceLines.map((line, index) => (
                  <p key={`${index}-${line}`} className="truncate text-[10px]">
                    {line}
                  </p>
                ))}
              </div>
              {s.invoiceShowAutomotiveImage && s.invoiceAutomotiveImageUrl && (
                <img
                  src={s.invoiceAutomotiveImageUrl}
                  alt="Illustration automobile de la facture"
                  className="max-h-20 w-[20%] shrink-0 object-contain"
                />
              )}
            </div>
            <p className="text-muted-foreground px-3 py-2 text-xs">
              Aperçu des zones du bandeau, des logos et du cachet dans son cadre — la facture émise
              est générée côté serveur.
            </p>
          </div>
        </Section>
      )}

      <Section title={t("settings.billing")}>
        <div className="space-y-1.5">
          <Label>{t("settings.currency")}</Label>
          <Input value="GNF" readOnly />
        </div>
        {text("vatRate", t("settings.vat"), "number")}
        {text("invoicePrefix", t("settings.invoicePrefix"))}
        <div className="space-y-1.5">
          <Label>{t("settings.printFormat")}</Label>
          <Select value={s.paperFormat} onValueChange={(v) => set("paperFormat", v as "A4" | "A5")}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="A4">A4</SelectItem>
              <SelectItem value="A5">A5</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="footer">{t("settings.invoiceFooter")}</Label>
          <Textarea
            id="footer"
            value={s.invoiceFooter}
            onChange={(e) => set("invoiceFooter", e.target.value)}
          />
        </div>
        <label className="flex items-center justify-between gap-3 rounded border p-3">
          <span className="text-sm">{t("settings.showPartner")}</span>
          <Switch
            checked={s.showPartnerOnDocs}
            onCheckedChange={(v) => set("showPartnerOnDocs", v)}
          />
        </label>
        <label className="flex items-center justify-between gap-3 rounded border p-3">
          <span className="text-sm">{t("settings.printQr")}</span>
          <Switch checked={s.printQrOnDocs} onCheckedChange={(v) => set("printQrOnDocs", v)} />
        </label>
        <p className="text-muted-foreground text-sm sm:col-span-2">
          {t("settings.invoiceSignNote")}
        </p>
      </Section>

      {isAdmin && (
        <Section title={t("settings.exchangeRateTitle")}>
          <p className="text-muted-foreground text-sm sm:col-span-2">
            {t("settings.exchangeRateDescription")}
          </p>
          <div className="rounded-md border p-3 text-sm sm:col-span-2">
            {(() => {
              const today = localDateInputValue();
              const currentRate = (exchangeRates ?? []).find(
                (rate) => rate.effective_date <= today,
              );
              return currentRate ? (
                <p>
                  {t("settings.exchangeRate")}: <strong>{currentRate.rate} GNF/USD</strong> ·{" "}
                  {currentRate.effective_date}
                </p>
              ) : (
                <p className="text-destructive">{t("settings.exchangeRateMissing")}</p>
              );
            })()}
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.exchangeRate")}</Label>
            <Input
              type="number"
              min="0.000001"
              step="0.000001"
              value={rateForm.rate}
              onChange={(event) => setRateForm({ ...rateForm, rate: event.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("settings.exchangeRateDate")}</Label>
            <Input
              type="date"
              value={rateForm.effective_date}
              onChange={(event) => setRateForm({ ...rateForm, effective_date: event.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <Button
              onClick={() => saveExchangeRate.mutate()}
              disabled={
                !rateForm.rate ||
                Number(rateForm.rate) <= 0 ||
                !rateForm.effective_date ||
                saveExchangeRate.isPending
              }
            >
              {t("settings.exchangeRateSave")}
            </Button>
          </div>
          <div className="space-y-2 sm:col-span-2">
            <h3 className="text-sm font-semibold">{t("settings.exchangeRateHistory")}</h3>
            {(exchangeRates ?? []).slice(0, 10).map((rate) => (
              <div
                key={rate.id}
                className="flex flex-wrap justify-between gap-2 border-b py-2 text-sm"
              >
                <span>{rate.effective_date}</span>
                <span>{rate.rate} GNF/USD</span>
                <span className="text-muted-foreground">
                  {t("settings.exchangeRateBy")}: {rate.created_by_name || "—"}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title={t("settings.documents")}>
        {text("orderPrefix", t("settings.orderPrefix"))}
        {text("deliveryPrefix", t("settings.deliveryPrefix"))}
        {text("printCopies", t("settings.printCopies"), "number")}
        {text("website", t("settings.website"))}
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="wa">{t("settings.defaultWhatsapp")}</Label>
          <Textarea
            id="wa"
            value={s.whatsappMessage}
            onChange={(e) => set("whatsappMessage", e.target.value)}
          />
        </div>
      </Section>

      <Section title={t("settings.payment")}>
        {text("bankName", t("settings.bank"))}
        {text("bankAccount", t("settings.bankAccount"))}
        {text("mobileMoney", t("settings.mobileMoney"))}
        {text("openingHours", t("settings.openingHours"))}
      </Section>

      <Section title={t("settings.reminders")}>
        <label className="flex items-center justify-between gap-3 rounded border p-3 sm:col-span-2">
          <span className="text-sm">{t("settings.weeklyReminders")}</span>
          <Switch
            checked={creditReminders.enabled}
            onCheckedChange={(enabled) =>
              setCreditReminders((current) => ({ ...current, enabled }))
            }
          />
        </label>
        <div className="space-y-1.5">
          <Label htmlFor="credit-reminder-frequency">{t("settings.frequency")}</Label>
          <Select
            value={creditReminders.frequency}
            onValueChange={(frequency) =>
              setCreditReminders((current) => ({ ...current, frequency: frequency as "weekly" }))
            }
          >
            <SelectTrigger id="credit-reminder-frequency">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="weekly">{t("settings.everyWeek")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="credit-reminder-day">{t("settings.sendDay")}</Label>
          <Select
            value={String(creditReminders.day_of_week)}
            onValueChange={(day) =>
              setCreditReminders((current) => ({ ...current, day_of_week: Number(day) }))
            }
          >
            <SelectTrigger id="credit-reminder-day">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {t("settings.weekdays")
                .split(",")
                .map((day, index) => (
                  <SelectItem key={index} value={String(index)}>
                    {day}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="credit-reminder-time">{t("settings.sendTime")}</Label>
          <Input
            id="credit-reminder-time"
            type="time"
            value={creditReminders.time}
            onChange={(event) =>
              setCreditReminders((current) => ({ ...current, time: event.target.value }))
            }
          />
          <p className="text-muted-foreground text-xs">
            {t("settings.timezone")}: {creditReminders.timezone}. {t("settings.settledExcluded")}
          </p>
        </div>
      </Section>

      <Section title={t("settings.stockSales")}>
        {text("lowStockThreshold", t("settings.lowStock"), "number")}
        {text("defaultMarginPct", t("settings.defaultMargin"), "number")}
        <label className="flex items-center justify-between gap-3 rounded border p-3 sm:col-span-2">
          <span className="text-sm">{t("settings.allowOverselling")}</span>
          <Switch
            checked={s.allowNegativeSale}
            onCheckedChange={(v) => set("allowNegativeSale", v)}
          />
        </label>
      </Section>

      <Section title={t("settings.securityLanguage")}>
        {text("sessionMinutes", t("settings.sessionMinutes"), "number")}
        <div className="space-y-1.5">
          <Label>{t("settings.language")}</Label>
          <Select
            value={language}
            onValueChange={(value) => {
              void changeLanguage(value as Language)
                .then(() => set("language", value as Language))
                .catch((error: unknown) => {
                  toast.error(t("settings.languageSaveError"), {
                    description: error instanceof Error ? error.message : t("common.unknownError"),
                  });
                });
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fr">{t("settings.languageFrench")}</SelectItem>
              <SelectItem value="en">{t("settings.languageEnglish")}</SelectItem>
              <SelectItem value="ar">{t("settings.languageArabic")}</SelectItem>
              <SelectItem value="zh">{t("settings.languageChinese")}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-muted-foreground text-xs">{t("settings.languageHint")}</p>
        </div>
      </Section>

      <Section title={t("settings.backup")}>
        <Button
          variant="outline"
          onClick={() => {
            const blob = new Blob([JSON.stringify(s, null, 2)], { type: "application/json" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "parametres-djibexa.json";
            a.click();
          }}
        >
          <Download className="size-4" /> {t("settings.export")}
        </Button>
        <Button variant="outline" asChild>
          <label className="cursor-pointer">
            <Upload className="size-4" /> {t("settings.import")}
            <input
              type="file"
              accept="application/json"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                try {
                  const next = {
                    ...DEFAULT_SETTINGS,
                    ...JSON.parse(await f.text()),
                    currency: "GNF",
                  };
                  setS(next);
                  saveSettings(next);
                  toast.success(t("settings.imported"));
                } catch {
                  toast.error(t("settings.invalidFile"));
                }
              }}
            />
          </label>
        </Button>
        <p className="text-muted-foreground text-xs sm:col-span-2">{t("settings.backupHint")}</p>
      </Section>
    </div>
  );
}
