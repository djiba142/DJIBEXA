import { createFileRoute, Link } from "@tanstack/react-router";
import { CircleHelp, Menu, ShieldCheck } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { brandLogo } from "@/lib/brand-assets";
import { useAuth } from "@/lib/auth";
import { useLocale, type Language } from "@/lib/locale";

export const PageRoute = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "DJIBEXA — Gestion d’entreprise" },
      {
        name: "description",
        content:
          "DJIBEXA centralise les ventes, les stocks, les achats, les factures et les rapports dans un espace de gestion sécurisé.",
      },
      { property: "og:title", content: "DJIBEXA — Gestion d’entreprise" },
      {
        property: "og:description",
        content: "Une plateforme de gestion conçue pour les entreprises et leurs équipes.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: PlatformLanding,
});

const PLATFORM_COPY: Record<
  Language,
  {
    title: string;
    description: string;
    navHelp: string;
    navLabel: string;
    openMenu: string;
    signIn: string;
    openErp: string;
    heroEyebrow: string;
    heroTitle: string;
    heroDescription: string;
    heroAction: string;
    privacyTitle: string;
    privacyDescription: string;
    privacyRoles: string;
    privacyAudit: string;
    ctaTitle: string;
    ctaDescription: string;
  }
> = {
  fr: {
    title: "DJIBEXA — Gestion d’entreprise",
    description:
      "DJIBEXA centralise les ventes, les stocks, les achats, les factures et les rapports dans un espace de gestion sécurisé.",
    navHelp: "Aide",
    navLabel: "Navigation principale",
    openMenu: "Ouvrir le menu",
    signIn: "Espace de gestion",
    openErp: "Ouvrir l’ERP",
    heroEyebrow: "La plateforme de gestion DJIBEXA",
    heroTitle: "Votre activité, mieux organisée.",
    heroDescription:
      "Gérez les opérations quotidiennes de votre entreprise dans un espace clair : ventes, produits, stocks, achats, factures et suivi financier.",
    heroAction: "Accéder à l’espace de gestion",
    privacyTitle: "Un espace de gestion pour chaque entreprise",
    privacyDescription:
      "Les comptes sont rattachés à leur entreprise. Les accès aux données et aux actions dépendent du rôle et des permissions de chaque utilisateur.",
    privacyRoles: "Accès organisé par rôle",
    privacyAudit: "Opérations métier tracées",
    ctaTitle: "Prêt à gérer votre activité ?",
    ctaDescription: "Connectez-vous à votre espace DJIBEXA pour continuer.",
  },
  en: {
    title: "DJIBEXA — Business management",
    description:
      "DJIBEXA brings sales, inventory, purchasing, invoices, and reports together in a secure workspace.",
    navHelp: "Help",
    navLabel: "Main navigation",
    openMenu: "Open menu",
    signIn: "Management portal",
    openErp: "Open the ERP",
    heroEyebrow: "The DJIBEXA management platform",
    heroTitle: "Your business, better organized.",
    heroDescription:
      "Manage your company's day-to-day operations in one clear workspace: sales, products, inventory, purchasing, invoices, and financial tracking.",
    heroAction: "Access the management portal",
    privacyTitle: "A management workspace for each company",
    privacyDescription:
      "Accounts are assigned to their company. Data and actions are accessible according to each user's role and permissions.",
    privacyRoles: "Role-based access",
    privacyAudit: "Business operations are traceable",
    ctaTitle: "Ready to manage your business?",
    ctaDescription: "Sign in to your DJIBEXA workspace to continue.",
  },
  ar: {
    title: "DJIBEXA — إدارة الأعمال",
    description: "تجمع DJIBEXA المبيعات والمخزون والمشتريات والفواتير والتقارير في مساحة آمنة.",
    navHelp: "المساعدة",
    navLabel: "التنقل الرئيسي",
    openMenu: "فتح القائمة",
    signIn: "بوابة الإدارة",
    openErp: "فتح النظام",
    heroEyebrow: "منصة DJIBEXA للإدارة",
    heroTitle: "أعمالك، بتنظيم أفضل.",
    heroDescription:
      "أدر العمليات اليومية لشركتك في مساحة واضحة: المبيعات والمنتجات والمخزون والمشتريات والفواتير والمتابعة المالية.",
    heroAction: "الدخول إلى بوابة الإدارة",
    privacyTitle: "مساحة إدارة خاصة بكل شركة",
    privacyDescription:
      "ترتبط الحسابات بشركاتها. ويعتمد الوصول إلى البيانات والإجراءات على دور كل مستخدم وصلاحياته.",
    privacyRoles: "صلاحيات حسب الدور",
    privacyAudit: "عمليات الأعمال قابلة للتتبع",
    ctaTitle: "هل أنت مستعد لإدارة نشاطك؟",
    ctaDescription: "سجل الدخول إلى مساحة DJIBEXA الخاصة بك للمتابعة.",
  },
  zh: {
    title: "DJIBEXA — 企业管理",
    description: "DJIBEXA 将销售、库存、采购、发票和报表整合到安全的管理空间中。",
    navHelp: "帮助",
    navLabel: "主导航",
    openMenu: "打开菜单",
    signIn: "管理入口",
    openErp: "打开 ERP",
    heroEyebrow: "DJIBEXA 管理平台",
    heroTitle: "让业务管理更有条理。",
    heroDescription:
      "在一个清晰的工作空间管理企业日常运营：销售、产品、库存、采购、发票和财务跟踪。",
    heroAction: "进入管理入口",
    privacyTitle: "每家企业拥有独立管理空间",
    privacyDescription: "账户关联到所属企业。数据和操作访问由每位用户的角色和权限控制。",
    privacyRoles: "基于角色的访问控制",
    privacyAudit: "业务操作可追溯",
    ctaTitle: "准备好管理业务了吗？",
    ctaDescription: "登录您的 DJIBEXA 工作空间以继续。",
  },
};

function PlatformLanding() {
  const { language, direction } = useLocale();
  const { session } = useAuth();
  const copy = PLATFORM_COPY[language];
  const accessPath = session ? "/dashboard" : "/auth";

  useEffect(() => {
    document.title = copy.title;
    const description = document.querySelector('meta[name="description"]');
    if (description instanceof HTMLMetaElement) description.content = copy.description;
    const openGraphTitle = document.querySelector('meta[property="og:title"]');
    if (openGraphTitle instanceof HTMLMetaElement) openGraphTitle.content = copy.title;
    const openGraphDescription = document.querySelector('meta[property="og:description"]');
    if (openGraphDescription instanceof HTMLMetaElement) {
      openGraphDescription.content = copy.description;
    }
  }, [copy.description, copy.title]);

  return (
    <div className="bg-background min-h-screen">
      <header className="border-b">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <Link to="/" aria-label="DJIBEXA" className="flex shrink-0 items-center">
            <img src={brandLogo} alt="DJIBEXA" className="h-10 w-36 object-contain" />
          </Link>
          <nav aria-label={copy.navLabel} className="hidden items-center gap-6 text-sm md:flex">
            <Link to="/aide" className="text-muted-foreground hover:text-foreground">
              {copy.navHelp}
            </Link>
          </nav>
          <div className="hidden items-center gap-3 md:flex">
            <Button asChild size="sm">
              <Link to={accessPath}>{session ? copy.openErp : copy.signIn}</Link>
            </Button>
          </div>
          <div className="flex items-center gap-2 md:hidden">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="icon" aria-label={copy.openMenu}>
                  <Menu aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent
                side={direction === "rtl" ? "left" : "right"}
                className="w-[min(20rem,85vw)]"
              >
                <SheetHeader>
                  <SheetTitle>DJIBEXA</SheetTitle>
                </SheetHeader>
                <nav aria-label={copy.navLabel} className="mt-6 flex flex-col gap-5">
                  <SheetClose asChild>
                    <Link to="/aide">{copy.navHelp}</Link>
                  </SheetClose>
                  <SheetClose asChild>
                    <Button asChild>
                      <Link to={accessPath}>{session ? copy.openErp : copy.signIn}</Link>
                    </Button>
                  </SheetClose>
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main>
        <section className="from-primary/10 via-background to-primary/5 bg-gradient-to-br px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="space-y-6">
              <p className="text-primary text-xs font-semibold tracking-[0.2em] uppercase">
                {copy.heroEyebrow}
              </p>
              <h1 className="font-display max-w-3xl text-4xl leading-tight font-bold tracking-tight sm:text-5xl lg:text-6xl">
                {copy.heroTitle}
              </h1>
              <p className="text-muted-foreground max-w-2xl text-base leading-7 sm:text-lg">
                {copy.heroDescription}
              </p>
              <Button asChild size="lg">
                <Link to={accessPath}>{session ? copy.openErp : copy.heroAction}</Link>
              </Button>
            </div>
          </div>
        </section>

        <section className="bg-muted/40 border-y">
          <div className="mx-auto grid max-w-7xl gap-6 px-4 py-12 sm:px-6 md:grid-cols-[auto_1fr] md:items-center lg:px-8">
            <div className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-xl">
              <ShieldCheck className="size-7" aria-hidden="true" />
            </div>
            <div>
              <h2 className="font-display text-xl font-bold sm:text-2xl">{copy.privacyTitle}</h2>
              <p className="text-muted-foreground mt-2 max-w-3xl leading-7">
                {copy.privacyDescription}
              </p>
              <div className="mt-4 flex flex-wrap gap-2 text-sm">
                <span className="bg-background rounded-full border px-3 py-1.5">
                  {copy.privacyRoles}
                </span>
                <span className="bg-background rounded-full border px-3 py-1.5">
                  {copy.privacyAudit}
                </span>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-14 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
          <div>
            <h2 className="font-display text-2xl font-bold">{copy.ctaTitle}</h2>
            <p className="text-muted-foreground mt-2">{copy.ctaDescription}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link to={accessPath}>{session ? copy.openErp : copy.signIn}</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/aide">
                <CircleHelp className="mr-2 size-4" aria-hidden="true" />
                {copy.navHelp}
              </Link>
            </Button>
          </div>
        </section>
      </main>
      <footer className="border-t px-4 py-6 text-center text-sm text-muted-foreground">
        DJIBEXA
      </footer>
    </div>
  );
}
