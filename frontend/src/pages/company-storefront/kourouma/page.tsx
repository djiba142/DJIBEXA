import { createFileRoute, Link } from "@tanstack/react-router";
import {
  BarChart3,
  Boxes,
  CircleHelp,
  Menu,
  MapPin,
  QrCode,
  Receipt,
  ShieldCheck,
  Sparkles,
  Truck,
  Warehouse,
} from "lucide-react";

import { brandLogo } from "@/lib/brand-assets";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import { useSettings } from "@/lib/settings";
import { PublicStorefrontPage } from "@/pages/company-storefront/public";
import { Clock, MessageCircle, Phone } from "lucide-react";
import { useEffect } from "react";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

export const PageRoute = createFileRoute("/entreprise/kourouma-auto-parts")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "DJIBEXA — Pièces auto à Madina, Conakry" },
      {
        name: "description",
        content:
          "DJIBEXA : pièces détachées automobiles d'origine à Madina, Conakry. Stock multi-dépôts, factures vérifiables par QR et partenaire officiel BSG Auto Parts.",
      },
      { property: "og:title", content: "DJIBEXA — Pièces auto à Madina, Conakry" },
      {
        property: "og:description",
        content: "Pièces d'origine, factures vérifiables par QR code et stock suivi en temps réel.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Landing,
});

const strengths = [
  { value: "100 %", key: "qr" },
  { value: "Multi-dépôts", key: "warehouses" },
  { value: "Temps réel", key: "realtime" },
  { value: "Officiel", key: "partner" },
];

const features = [
  { icon: Receipt, key: "sales" },
  { icon: Sparkles, key: "smartSearch" },
  { icon: Boxes, key: "stock" },
  { icon: Warehouse, key: "warehouses" },
  { icon: Truck, key: "orders" },
  { icon: QrCode, key: "qr" },
  { icon: BarChart3, key: "reports" },
  { icon: ShieldCheck, key: "security" },
];

const categories = [
  "braking",
  "filtration",
  "shockAbsorbers",
  "clutch",
  "engine",
  "belts",
  "lighting",
  "electrical",
  "steering",
  "cooling",
];

const steps = ["describePart", "verifiedStock", "qrInvoice", "verification"];

const reasons = [
  { icon: ShieldCheck, key: "genuineParts" },
  { icon: Boxes, key: "wholesaleRetail" },
  { icon: Truck, key: "availability" },
];

function Landing() {
  return <PublicStorefrontPage slug="kourouma-auto-parts" fallback={<LegacyLanding />} />;
}

function LegacyLanding() {
  const { t, direction } = useLocale();
  const { session } = useAuth();
  const settings = useSettings();
  const target = session ? "/dashboard" : "/auth";

  useEffect(() => {
    document.title = t("landing.documentTitle");
    const localizedMetadata = [
      { selector: 'meta[name="description"]', key: "landing.metaDescription" },
      { selector: 'meta[property="og:title"]', key: "landing.documentTitle" },
      { selector: 'meta[property="og:description"]', key: "landing.metaDescription" },
    ] as const;
    for (const { selector, key } of localizedMetadata) {
      const element = document.querySelector(selector);
      if (element instanceof HTMLMetaElement) element.content = t(key);
    }
  }, [t]);

  return (
    <div className="bg-background min-h-screen">
      <header className="flex items-center justify-between gap-3 p-4 md:px-10">
        <div className="flex items-center gap-3">
          <img src={brandLogo} alt={t("landing.logoAlt")} className="h-11 w-44 object-contain" />
        </div>
        <nav
          aria-label={t("landing.mainNavigation")}
          className="hidden items-center gap-6 text-sm md:flex"
        >
          <Link
            to="/aide"
            className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <CircleHelp aria-hidden="true" className="size-4" />
            {t("nav.help")}
          </Link>
          <a className="text-muted-foreground hover:text-foreground" href="#services">
            {t("landing.navServices")}
          </a>
          <a className="text-muted-foreground hover:text-foreground" href="#gammes">
            {t("landing.navCategories")}
          </a>
          <a className="text-muted-foreground hover:text-foreground" href="#contact">
            {t("landing.navContact")}
          </a>
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <LanguageSwitcher />
          <Button asChild size="sm">
            <Link to={target}>{session ? t("landing.openErp") : t("landing.personalSpace")}</Link>
          </Button>
        </div>
        <div className="flex items-center gap-2 md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" aria-label={t("landing.openMenu")}>
                <Menu aria-hidden="true" />
              </Button>
            </SheetTrigger>
            <SheetContent
              side={direction === "rtl" ? "left" : "right"}
              className="w-[min(20rem,85vw)]"
            >
              <SheetHeader>
                <SheetTitle>{t("landing.menuTitle")}</SheetTitle>
              </SheetHeader>
              <div className="mt-6">
                <LanguageSwitcher />
              </div>
              <nav aria-label={t("landing.mainNavigation")} className="mt-6 flex flex-col gap-4">
                <SheetClose asChild>
                  <a className="text-muted-foreground hover:text-foreground" href="#services">
                    {t("landing.navServices")}
                  </a>
                </SheetClose>
                <SheetClose asChild>
                  <a className="text-muted-foreground hover:text-foreground" href="#gammes">
                    {t("landing.navCategories")}
                  </a>
                </SheetClose>
                <SheetClose asChild>
                  <a className="text-muted-foreground hover:text-foreground" href="#contact">
                    {t("landing.navContact")}
                  </a>
                </SheetClose>
                <SheetClose asChild>
                  <Link
                    to="/aide"
                    className="text-muted-foreground hover:text-foreground flex items-center gap-2"
                  >
                    <CircleHelp aria-hidden="true" className="size-4" />
                    {t("nav.help")}
                  </Link>
                </SheetClose>
              </nav>
              <SheetClose asChild>
                <Button asChild className="mt-8 w-full">
                  <Link to={target}>
                    {session ? t("landing.openErp") : t("landing.personalSpace")}
                  </Link>
                </Button>
              </SheetClose>
            </SheetContent>
          </Sheet>
        </div>
      </header>

      <main>
        <section className="brand-gradient px-6 py-14 md:px-10 md:py-20">
          <div className="mx-auto grid max-w-6xl items-center gap-10 md:grid-cols-2">
            <div className="text-primary-foreground space-y-5">
              <p className="text-primary-foreground/70 text-xs tracking-[0.25em] uppercase">
                {t("landing.locationShort")}
              </p>
              <h1 className="text-4xl font-bold tracking-wide uppercase md:text-5xl">
                {t("landing.heroTitle")}
              </h1>
              <p className="text-primary-foreground/80 max-w-lg">{t("landing.heroDescription")}</p>
              <div className="flex flex-wrap gap-3">
                <Button asChild size="lg" variant="secondary">
                  <Link to={target}>
                    {session ? t("landing.dashboard") : t("landing.management")}
                  </Link>
                </Button>
                <Button
                  asChild
                  size="lg"
                  variant="outline"
                  className="border-white/50 bg-transparent text-white hover:bg-white/10 hover:text-white"
                >
                  <a href="#contact">{t("landing.findMadina")}</a>
                </Button>
              </div>
            </div>
            <div className="brand-gradient flex min-h-72 flex-col items-center justify-center gap-6 rounded-xl border border-white/15 p-6 text-center text-white shadow-xl sm:p-8">
              <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-lg sm:p-8">
                <img src={brandLogo} alt="" aria-hidden="true" className="w-full object-contain" />
              </div>
              <div>
                <p className="font-display text-xl font-extrabold tracking-wide uppercase sm:text-2xl">
                  {t("landing.bannerHeadline")}
                </p>
                <p className="mt-1 text-xs text-white/80 sm:text-sm">
                  {t("landing.bannerTagline")}
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b">
          <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px px-6 md:grid-cols-4 md:px-10">
            {strengths.map((s) => (
              <div key={s.key} className="py-6 text-center">
                <p className="font-display text-2xl font-bold uppercase">
                  {s.key === "qr" ? s.value : t(`landing.strengthValue.${s.key}`)}
                </p>
                <p className="text-muted-foreground text-xs">{t(`landing.strength.${s.key}`)}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="services" className="mx-auto max-w-6xl px-6 py-14 md:px-10">
          <h2 className="font-display text-2xl font-bold tracking-wide uppercase">
            {t("landing.servicesTitle")}
          </h2>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
            {t("landing.servicesDescription")}
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f) => (
              <div key={f.key} className="panel p-5">
                <f.icon className="text-primary size-6" />
                <h3 className="mt-3 font-semibold">{t(`landing.feature.${f.key}.title`)}</h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  {t(`landing.feature.${f.key}.description`)}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="bg-muted/40 border-y">
          <div className="mx-auto grid max-w-6xl items-center gap-8 px-6 py-12 md:grid-cols-2 md:px-10">
            <div className="flex items-center gap-5">
              <div
                aria-hidden="true"
                className="bg-background text-primary flex size-24 shrink-0 items-center justify-center rounded-lg border"
              >
                <Truck className="size-10" />
              </div>
              <div>
                <p className="text-muted-foreground text-xs tracking-widest uppercase">
                  {t("landing.officialPartner")}
                </p>
                <p className="font-display text-xl font-bold uppercase">BSG Auto Parts</p>
                <p className="text-muted-foreground text-sm">{t("landing.partnerTagline")}</p>
              </div>
            </div>
            <div className="panel flex items-start gap-3 p-5 text-sm">
              <QrCode className="text-primary mt-0.5 size-5 shrink-0" />
              <p>
                <strong>{t("landing.invoiceQuestion")}</strong> {t("landing.invoiceExplanation")}
              </p>
            </div>
          </div>
        </section>

        <section id="gammes" className="mx-auto max-w-6xl px-6 py-14 md:px-10">
          <h2 className="font-display text-2xl font-bold tracking-wide uppercase">
            {t("landing.categoriesTitle")}
          </h2>
          <div className="mt-5 flex flex-wrap gap-2">
            {categories.map((category) => (
              <span
                key={category}
                className="bg-muted rounded-full border px-4 py-1.5 text-sm font-medium"
              >
                {t(`landing.category.${category}`)}
              </span>
            ))}
          </div>
        </section>

        <section className="bg-muted/40 border-y">
          <div className="mx-auto grid max-w-6xl gap-8 px-6 py-12 md:grid-cols-[1fr_1.2fr] md:items-center md:px-10">
            <div>
              <p className="text-primary text-xs font-semibold tracking-[0.2em] uppercase">
                {t("landing.searchPreparation")}
              </p>
              <h2 className="font-display mt-2 text-2xl font-bold tracking-wide uppercase">
                {t("landing.findPartTitle")}
              </h2>
              <p className="text-muted-foreground mt-2 text-sm">
                {t("landing.findPartDescription")}
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ["vehicle", "vehicleDetails"],
                ["engineType", "engineDetails"],
                ["reference", "referenceDetails"],
                ["need", "needDetails"],
              ].map(([title, detail], index) => (
                <div key={title} className="panel flex items-start gap-3 p-4">
                  <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-bold">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <h3 className="font-semibold">{t(`landing.search.${title}`)}</h3>
                    <p className="text-muted-foreground mt-1 text-sm">
                      {t(`landing.search.${detail}`)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-muted/40 border-y">
          <div className="mx-auto max-w-6xl px-6 py-14 md:px-10">
            <h2 className="font-display text-2xl font-bold tracking-wide uppercase">
              {t("landing.howTitle")}
            </h2>
            <div className="mt-6 grid gap-4 md:grid-cols-4">
              {steps.map((step, i) => (
                <div key={step} className="panel p-5">
                  <p className="font-display text-primary text-3xl font-bold">0{i + 1}</p>
                  <h3 className="mt-2 font-semibold">{t(`landing.step.${step}.title`)}</h3>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {t(`landing.step.${step}.description`)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-14 md:px-10">
          <h2 className="font-display text-2xl font-bold tracking-wide uppercase">
            {t("landing.whyChoose")}
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {reasons.map((r) => (
              <div key={r.key} className="panel flex gap-3 p-5">
                <r.icon className="text-primary mt-0.5 size-5 shrink-0" />
                <div>
                  <h3 className="font-semibold">{t(`landing.reason.${r.key}.title`)}</h3>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {t(`landing.reason.${r.key}.description`)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section id="contact" className="mx-auto max-w-6xl px-6 pb-4 md:px-10">
          <div className="panel grid gap-4 p-6 sm:grid-cols-3">
            <div className="flex items-start gap-3">
              <Clock className="text-primary mt-0.5 size-5 shrink-0" />
              <div>
                <p className="font-semibold">{t("landing.hours")}</p>
                <p className="text-muted-foreground text-sm">{settings.openingHours}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Phone className="text-primary mt-0.5 size-5 shrink-0" />
              <div>
                <p className="font-semibold">{t("landing.phone")}</p>
                <p className="text-muted-foreground text-sm">
                  {settings.phone || t("landing.phoneFallback")}
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <MessageCircle className="text-primary mt-0.5 size-5 shrink-0" />
              <div>
                <p className="font-semibold">WhatsApp</p>
                {settings.whatsapp ? (
                  <a
                    className="text-primary text-sm underline"
                    href={`https://wa.me/${settings.whatsapp.replace(/\D/g, "")}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {settings.whatsapp}
                  </a>
                ) : (
                  <p className="text-muted-foreground text-sm">{t("landing.comingSoon")}</p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-12 md:px-10">
          <div className="panel flex flex-wrap items-center justify-between gap-4 p-6">
            <div className="flex items-start gap-3">
              <MapPin className="text-primary mt-0.5 size-5 shrink-0" />
              <div>
                <p className="font-semibold">{t("landing.findUs")}</p>
                <p className="text-muted-foreground text-sm">{t("landing.fullAddress")}</p>
              </div>
            </div>
            <Button asChild>
              <Link to={target}>{t("landing.personalSpace")}</Link>
            </Button>
          </div>
        </section>

        <section className="brand-gradient px-6 py-12 text-primary-foreground md:px-10">
          <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-5 sm:flex-row sm:items-center">
            <div>
              <h2 className="font-display text-2xl font-bold uppercase">{t("landing.ctaTitle")}</h2>
              <p className="mt-2 max-w-2xl text-sm text-primary-foreground/80">
                {t("landing.ctaDescription")}
              </p>
            </div>
            {settings.whatsapp ? (
              <Button asChild variant="secondary">
                <a
                  href={`https://wa.me/${settings.whatsapp.replace(/\D/g, "")}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <MessageCircle />
                  {t("landing.writeWhatsApp")}
                </a>
              </Button>
            ) : (
              <Button asChild variant="secondary">
                <a href="#contact">{t("landing.viewContact")}</a>
              </Button>
            )}
          </div>
        </section>
      </main>

      <footer className="text-muted-foreground border-t px-6 py-6 text-xs md:px-10">
        {t("landing.footer", { year: new Date().getFullYear() })}
      </footer>
    </div>
  );
}
