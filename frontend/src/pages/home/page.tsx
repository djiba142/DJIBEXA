import { Link } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  Boxes,
  CircleHelp,
  ClipboardList,
  Menu,
  PackageCheck,
  Receipt,
  ShieldCheck,
  ShoppingCart,
  UsersRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { InstallAppButton } from "@/components/InstallAppButton";
import { useAuth } from "@/lib/auth";
import { useLocale, type Language } from "@/lib/locale";
import { api } from "@/lib/api";

type HomeCopy = {
  title: string;
  description: string;
  navLabel: string;
  openMenu: string;
  home: string;
  solution: string;
  featuresNav: string;
  faqNav: string;
  contact: string;
  portal: string;
  heroEyebrow: string;
  heroTitle: string;
  heroDescription: string;
  discover: string;
  demoAction: string;
  heroImageAlt: string;
  heroImageCaption: string;
  visionTitle: string;
  visionDescription: string;
  visionSteps: { title: string; description: string }[];
  featuresTitle: string;
  featuresDescription: string;
  features: { title: string; description: string }[];
  operationsTitle: string;
  operationsDescription: string;
  operations: string[];
  operationsImageAlt: string;
  operationsImageCaption: string;
  companiesTitle: string;
  companiesDescription: string;
  companies: string[];
  approachTitle: string;
  approachDescription: string;
  approachSteps: { title: string; description: string }[];
  faqTitle: string;
  faqDescription: string;
  faqs: { question: string; answer: string }[];
  demoTitle: string;
  demoDescription: string;
  demoCompany: string;
  demoContactName: string;
  demoEmail: string;
  demoPhone: string;
  demoMessage: string;
  demoConsent: string;
  demoSubmit: string;
  demoSubmitting: string;
  demoSuccess: string;
  demoError: string;
  ctaTitle: string;
  ctaDescription: string;
  contactTitle: string;
  contactDescription: string;
  privacyTitle: string;
  privacyDescription: string;
  footerDescription: string;
};

const HOME_COPY: Record<Language, HomeCopy> = {
  fr: {
    title: "DJIBEXA — Solution numérique de gestion",
    description:
      "DJIBEXA aide les entreprises à organiser leurs ventes, stocks, achats, clients et rapports dans un espace de gestion.",
    navLabel: "Navigation principale",
    openMenu: "Ouvrir le menu",
    home: "Accueil",
    solution: "Solution",
    featuresNav: "Fonctionnalités",
    faqNav: "FAQ",
    contact: "En savoir plus",
    portal: "Connexion",
    heroEyebrow: "Solution numérique de gestion",
    heroTitle: "Votre entreprise mérite une gestion plus claire.",
    heroDescription:
      "Organisez vos activités, suivez vos opérations et prenez vos décisions à partir d’informations réunies dans un même espace.",
    discover: "Découvrir DJIBEXA",
    demoAction: "Demander une démonstration",
    heroImageAlt: "Photo d’illustration d’un bureau moderne et lumineux",
    heroImageCaption: "Un environnement de travail professionnel, à l’image de votre organisation.",
    visionTitle: "Une vision globale de votre activité",
    visionDescription:
      "Les outils de gestion réunissent les tâches essentielles pour mieux structurer le travail quotidien.",
    visionSteps: [
      {
        title: "Organiser",
        description: "Rassemblez les opérations dans un espace de travail structuré.",
      },
      {
        title: "Suivre",
        description: "Consultez les informations utiles au suivi des activités.",
      },
      {
        title: "Décider",
        description: "Appuyez vos décisions sur les données disponibles dans l’application.",
      },
    ],
    featuresTitle: "Les fonctions essentielles",
    featuresDescription:
      "Des fonctions de gestion réunies dans DJIBEXA, selon les modules disponibles pour votre espace.",
    features: [
      { title: "Ventes", description: "Enregistrez et consultez les opérations de vente." },
      { title: "Stocks", description: "Suivez les produits et les mouvements de stock." },
      { title: "Achats", description: "Organisez les commandes et les réceptions." },
      { title: "Clients", description: "Retrouvez les informations liées à vos clients." },
      { title: "Documents", description: "Gérez les factures et les documents associés." },
      { title: "Rapports", description: "Consultez les rapports disponibles dans l’application." },
    ],
    operationsTitle: "Organiser et suivre les opérations",
    operationsDescription:
      "Des repères communs aident les équipes à retrouver les informations et à suivre le déroulement du travail.",
    operations: [
      "Des informations rassemblées par activité.",
      "Des accès adaptés aux rôles et permissions des utilisateurs.",
      "Des opérations métier consignées dans l’application.",
    ],
    operationsImageAlt: "Photo d’illustration d’un rayon de pièces automobiles et de stockage",
    operationsImageCaption:
      "Photo d’illustration : ce rayon ne représente pas une capture de l’application DJIBEXA.",
    companiesTitle: "Une solution adaptée à votre organisation",
    companiesDescription:
      "Chaque entreprise conserve son espace de gestion et, si elle le souhaite, sa vitrine publique avec son identité et son contenu propres.",
    companies: [
      "Un espace rattaché à l’entreprise concernée.",
      "Une identité de vitrine configurée séparément.",
      "Des informations d’entreprise qui restent propres à chaque espace.",
    ],
    approachTitle: "La démarche DJIBEXA",
    approachDescription:
      "Une présentation responsable de l’outil : des fonctions concrètes, des accès encadrés et une information lisible.",
    approachSteps: [
      {
        title: "Des fonctions concrètes",
        description: "La présentation porte sur les fonctions déjà disponibles dans l’application.",
      },
      {
        title: "Des accès encadrés",
        description: "Les permissions déterminent les données et actions accessibles.",
      },
      {
        title: "Une activité traçable",
        description:
          "Les opérations enregistrées peuvent être consultées selon les droits accordés.",
      },
    ],
    faqTitle: "Questions fréquentes",
    faqDescription:
      "Quelques repères pour comprendre DJIBEXA, ses espaces de gestion et les fonctions présentées.",
    faqs: [
      {
        question: "À quoi sert DJIBEXA ?",
        answer:
          "DJIBEXA est une solution numérique de gestion d’entreprise. Elle rassemble des fonctions comme les ventes, les stocks, les achats, les clients, les documents et les rapports.",
      },
      {
        question: "Toutes les fonctions sont-elles disponibles dans chaque espace ?",
        answer:
          "Les fonctions visibles dépendent des modules disponibles et des permissions attribuées à votre compte.",
      },
      {
        question: "Les vitrines des entreprises sont-elles séparées de DJIBEXA ?",
        answer:
          "Oui. La page publique DJIBEXA présente la solution. Chaque vitrine d’entreprise conserve son identité et son contenu propres.",
      },
      {
        question: "Comment me connecter ?",
        answer:
          "L’accès est réservé aux utilisateurs autorisés. Utilisez l’identifiant ou l’adresse e-mail et le mot de passe associés à votre compte.",
      },
      {
        question: "Comment demander une démonstration ?",
        answer:
          "Remplissez le formulaire de demande en bas de cette page. L’équipe DJIBEXA pourra vous recontacter.",
      },
    ],
    demoTitle: "Demander une démonstration",
    demoDescription:
      "Présentez brièvement votre entreprise et votre besoin. Ces informations seront accessibles uniquement à l’administration centrale DJIBEXA pour donner suite à votre demande.",
    demoCompany: "Nom de l’entreprise",
    demoContactName: "Votre nom",
    demoEmail: "Adresse e-mail professionnelle",
    demoPhone: "Téléphone (facultatif)",
    demoMessage: "Que souhaitez-vous découvrir ?",
    demoConsent: "J’accepte que DJIBEXA utilise ces coordonnées pour répondre à ma demande.",
    demoSubmit: "Envoyer ma demande",
    demoSubmitting: "Envoi en cours…",
    demoSuccess: "Votre demande a bien été enregistrée. L’équipe DJIBEXA pourra vous recontacter.",
    demoError: "Votre demande n’a pas pu être envoyée. Vérifiez votre connexion et réessayez.",
    ctaTitle: "Donnez plus de clarté à votre gestion.",
    ctaDescription: "Demandez une démonstration ou connectez-vous à DJIBEXA.",
    contactTitle: "En savoir plus sur DJIBEXA",
    contactDescription:
      "Parcourez les informations disponibles sur cette page. Si vous avez déjà un compte, connectez-vous à DJIBEXA.",
    privacyTitle: "Respect des espaces d’entreprise",
    privacyDescription:
      "La page DJIBEXA présente la solution. Les vitrines et les contenus propres à chaque entreprise restent séparés.",
    footerDescription: "Solution numérique de gestion d’entreprise.",
  },
  en: {
    title: "DJIBEXA — Business management solution",
    description:
      "DJIBEXA helps businesses organize sales, inventory, purchasing, customers, and reports in a management workspace.",
    navLabel: "Main navigation",
    openMenu: "Open menu",
    home: "Home",
    solution: "Solution",
    featuresNav: "Features",
    faqNav: "FAQ",
    contact: "Learn more",
    portal: "Sign in",
    heroEyebrow: "Digital business management solution",
    heroTitle: "Your business deserves clearer management.",
    heroDescription:
      "Organize your work, follow operations, and make decisions using information brought together in one workspace.",
    discover: "Discover DJIBEXA",
    demoAction: "Request a demonstration",
    heroImageAlt: "Illustrative photo of a bright, modern office",
    heroImageCaption: "A professional work environment shaped around your organization.",
    visionTitle: "A complete view of your business",
    visionDescription:
      "Management tools bring essential tasks together to structure everyday work.",
    visionSteps: [
      { title: "Organize", description: "Bring operations together in a structured workspace." },
      { title: "Follow", description: "Review information that helps track activities." },
      {
        title: "Decide",
        description: "Use information available in the application to guide decisions.",
      },
    ],
    featuresTitle: "Essential functions",
    featuresDescription:
      "Management functions brought together in DJIBEXA, according to the modules available in your workspace.",
    features: [
      { title: "Sales", description: "Record and review sales operations." },
      { title: "Inventory", description: "Track products and stock movements." },
      { title: "Purchasing", description: "Organize orders and receipts." },
      { title: "Customers", description: "Find information related to your customers." },
      { title: "Documents", description: "Manage invoices and related documents." },
      { title: "Reports", description: "Review reports available in the application." },
    ],
    operationsTitle: "Organize and follow operations",
    operationsDescription:
      "Shared reference points help teams find information and follow how work progresses.",
    operations: [
      "Information grouped by activity.",
      "Access based on users’ roles and permissions.",
      "Business operations recorded in the application.",
    ],
    operationsImageAlt: "Illustrative photo of automotive parts displayed on storage shelves",
    operationsImageCaption:
      "Illustrative photo: this shelf is not a screenshot of the DJIBEXA application.",
    companiesTitle: "A solution adapted to your organization",
    companiesDescription:
      "Each company keeps its own management workspace and, if desired, its own public storefront and identity.",
    companies: [
      "A workspace associated with the relevant company.",
      "A separately configured storefront identity.",
      "Company information kept separate for each workspace.",
    ],
    approachTitle: "The DJIBEXA approach",
    approachDescription:
      "A responsible presentation of the tool: practical functions, controlled access, and clear information.",
    approachSteps: [
      {
        title: "Practical functions",
        description: "The presentation focuses on functions already available in the application.",
      },
      {
        title: "Controlled access",
        description: "Permissions determine which data and actions users can access.",
      },
      {
        title: "Traceable activity",
        description: "Recorded operations can be reviewed according to granted permissions.",
      },
    ],
    faqTitle: "Frequently asked questions",
    faqDescription:
      "A few useful details about DJIBEXA, its workspaces, and the functions presented here.",
    faqs: [
      {
        question: "What is DJIBEXA for?",
        answer:
          "DJIBEXA is a digital business management solution. It brings together functions such as sales, inventory, purchasing, customers, documents, and reports.",
      },
      {
        question: "Are all functions available in every workspace?",
        answer:
          "Available functions depend on the modules enabled for your workspace and the permissions assigned to your account.",
      },
      {
        question: "Are company storefronts separate from DJIBEXA?",
        answer:
          "Yes. The public DJIBEXA page presents the solution. Each company storefront keeps its own identity and content.",
      },
      {
        question: "How do I sign in?",
        answer:
          "Access is limited to authorized users. Sign in with the username or email address and password linked to your account.",
      },
      {
        question: "How can I request a demonstration?",
        answer:
          "Complete the request form at the bottom of this page. The DJIBEXA team may follow up.",
      },
    ],
    demoTitle: "Request a demonstration",
    demoDescription:
      "Tell us briefly about your business and what you would like to explore. These details are only accessible to DJIBEXA central administration so they can respond to your request.",
    demoCompany: "Company name",
    demoContactName: "Your name",
    demoEmail: "Business email address",
    demoPhone: "Phone (optional)",
    demoMessage: "What would you like to explore?",
    demoConsent: "I agree that DJIBEXA may use these contact details to respond to my request.",
    demoSubmit: "Send my request",
    demoSubmitting: "Sending…",
    demoSuccess: "Your request has been recorded. The DJIBEXA team may contact you.",
    demoError: "We could not send your request. Check your connection and try again.",
    ctaTitle: "Bring more clarity to your management.",
    ctaDescription: "Request a demonstration or sign in to DJIBEXA.",
    contactTitle: "Learn more about DJIBEXA",
    contactDescription:
      "Browse the information on this page. If you already have an account, sign in to DJIBEXA.",
    privacyTitle: "Respecting company workspaces",
    privacyDescription:
      "The DJIBEXA page presents the solution. Each company’s storefront and content remain separate.",
    footerDescription: "Digital business management solution.",
  },
  ar: {
    title: "DJIBEXA — حل رقمي لإدارة الأعمال",
    description: "تساعد DJIBEXA الشركات على تنظيم المبيعات والمخزون والمشتريات والعملاء والتقارير.",
    navLabel: "التنقل الرئيسي",
    openMenu: "فتح القائمة",
    home: "الرئيسية",
    solution: "الحل",
    featuresNav: "الميزات",
    faqNav: "الأسئلة الشائعة",
    contact: "معلومات إضافية",
    portal: "تسجيل الدخول",
    heroEyebrow: "حل رقمي لإدارة الأعمال",
    heroTitle: "تستحق شركتك إدارة أكثر وضوحًا.",
    heroDescription:
      "نظّم أعمالك وتابع العمليات واتخذ قراراتك باستخدام معلومات مجمعة في مساحة واحدة.",
    discover: "اكتشف DJIBEXA",
    demoAction: "طلب عرض توضيحي",
    heroImageAlt: "صورة توضيحية لمكتب حديث ومشرق",
    heroImageCaption: "بيئة عمل مهنية تتناسب مع تنظيم مؤسستك.",
    visionTitle: "رؤية شاملة لنشاطك",
    visionDescription: "تجمع أدوات الإدارة المهام الأساسية لتنظيم العمل اليومي.",
    visionSteps: [
      { title: "نظّم", description: "اجمع العمليات في مساحة عمل منظمة." },
      { title: "تابع", description: "راجع المعلومات المفيدة لمتابعة الأنشطة." },
      { title: "قرّر", description: "استند إلى المعلومات المتاحة في التطبيق." },
    ],
    featuresTitle: "الوظائف الأساسية",
    featuresDescription: "وظائف إدارة مجمعة في DJIBEXA وفقًا للوحدات المتاحة في مساحتك.",
    features: [
      { title: "المبيعات", description: "سجّل عمليات البيع وراجعها." },
      { title: "المخزون", description: "تابع المنتجات وحركات المخزون." },
      { title: "المشتريات", description: "نظّم الطلبات والاستلامات." },
      { title: "العملاء", description: "اعثر على المعلومات المتعلقة بعملائك." },
      { title: "المستندات", description: "أدر الفواتير والمستندات المرتبطة بها." },
      { title: "التقارير", description: "راجع التقارير المتاحة في التطبيق." },
    ],
    operationsTitle: "تنظيم العمليات ومتابعتها",
    operationsDescription:
      "تساعد المعلومات المشتركة الفرق على العثور على البيانات ومتابعة سير العمل.",
    operations: [
      "معلومات مجمعة حسب النشاط.",
      "صلاحيات وصول وفق أدوار المستخدمين.",
      "تسجيل العمليات في التطبيق.",
    ],
    operationsImageAlt: "صورة توضيحية لرفوف تخزين قطع غيار السيارات",
    operationsImageCaption: "صورة توضيحية؛ هذا الرف ليس لقطة شاشة من تطبيق DJIBEXA.",
    companiesTitle: "حل يتكيف مع مؤسستك",
    companiesDescription: "تحتفظ كل شركة بمساحة إدارتها الخاصة وبواجهة عرض عامة مستقلة عند الحاجة.",
    companies: [
      "مساحة مرتبطة بالشركة المعنية.",
      "هوية واجهة عرض مضبوطة بشكل منفصل.",
      "معلومات مستقلة لكل مساحة.",
    ],
    approachTitle: "نهج DJIBEXA",
    approachDescription: "عرض مسؤول للأداة: وظائف عملية، وصول مضبوط ومعلومات واضحة.",
    approachSteps: [
      { title: "وظائف عملية", description: "يعرض الموقع الوظائف المتاحة بالفعل في التطبيق." },
      { title: "وصول مضبوط", description: "تحدد الصلاحيات البيانات والإجراءات المتاحة." },
      { title: "نشاط قابل للتتبع", description: "يمكن مراجعة العمليات المسجلة وفق الصلاحيات." },
    ],
    faqTitle: "الأسئلة الشائعة",
    faqDescription: "معلومات مفيدة عن DJIBEXA ومساحات الإدارة والوظائف المعروضة.",
    faqs: [
      {
        question: "ما الغرض من DJIBEXA؟",
        answer:
          "DJIBEXA حل رقمي لإدارة الأعمال، يجمع وظائف مثل المبيعات والمخزون والمشتريات والعملاء والمستندات والتقارير.",
      },
      {
        question: "هل تتوفر جميع الوظائف في كل مساحة؟",
        answer: "تعتمد الوظائف المتاحة على الوحدات المفعّلة والصلاحيات الممنوحة لحسابك.",
      },
      {
        question: "هل واجهات عرض الشركات منفصلة عن DJIBEXA؟",
        answer:
          "نعم. تعرض صفحة DJIBEXA العامة الحل، بينما تحتفظ واجهة كل شركة بهويتها ومحتواها الخاصين.",
      },
      {
        question: "كيف يمكنني تسجيل الدخول؟",
        answer:
          "الدخول مخصص للمستخدمين المصرح لهم. استخدم اسم المستخدم أو البريد الإلكتروني وكلمة المرور المرتبطة بحسابك.",
      },
      {
        question: "كيف أطلب عرضًا توضيحيًا؟",
        answer: "املأ نموذج الطلب أسفل هذه الصفحة. قد يتواصل معك فريق DJIBEXA للمتابعة.",
      },
    ],
    demoTitle: "طلب عرض توضيحي",
    demoDescription:
      "عرّفنا بإيجاز على مؤسستك وما ترغب في استكشافه. لا يمكن الاطلاع على هذه المعلومات إلا من قبل الإدارة المركزية لـ DJIBEXA لمتابعة طلبك.",
    demoCompany: "اسم المؤسسة",
    demoContactName: "اسمك",
    demoEmail: "عنوان البريد الإلكتروني للعمل",
    demoPhone: "الهاتف (اختياري)",
    demoMessage: "ما الذي ترغب في استكشافه؟",
    demoConsent: "أوافق على استخدام DJIBEXA لبيانات الاتصال للرد على طلبي.",
    demoSubmit: "إرسال طلبي",
    demoSubmitting: "جارٍ الإرسال…",
    demoSuccess: "تم تسجيل طلبك. قد يتواصل معك فريق DJIBEXA.",
    demoError: "تعذر إرسال الطلب. تحقق من الاتصال وحاول مرة أخرى.",
    ctaTitle: "اجعل إدارة أعمالك أكثر وضوحًا.",
    ctaDescription: "اطلب عرضًا توضيحيًا أو سجّل الدخول إلى DJIBEXA.",
    contactTitle: "معلومات إضافية عن DJIBEXA",
    contactDescription:
      "تصفح المعلومات المتاحة في هذه الصفحة. إذا كان لديك حساب، فسجّل الدخول إلى DJIBEXA.",
    privacyTitle: "احترام مساحات الشركات",
    privacyDescription: "تعرض صفحة DJIBEXA الحل، بينما تبقى واجهات ومحتويات الشركات منفصلة.",
    footerDescription: "حل رقمي لإدارة الأعمال.",
  },
  zh: {
    title: "DJIBEXA — 数字化企业管理方案",
    description: "DJIBEXA 帮助企业在管理空间中组织销售、库存、采购、客户和报表。",
    navLabel: "主导航",
    openMenu: "打开菜单",
    home: "首页",
    solution: "解决方案",
    featuresNav: "功能",
    faqNav: "常见问题",
    contact: "了解更多",
    portal: "登录",
    heroEyebrow: "数字化企业管理方案",
    heroTitle: "让企业管理更加清晰。",
    heroDescription: "在一个空间中组织工作、跟踪运营，并依据汇总的信息作出决策。",
    discover: "了解 DJIBEXA",
    demoAction: "申请演示",
    heroImageAlt: "现代明亮办公室的示意照片",
    heroImageCaption: "专业的工作环境，适应您的组织方式。",
    visionTitle: "全面了解您的业务",
    visionDescription: "管理工具汇集日常工作所需的基本任务。",
    visionSteps: [
      { title: "组织", description: "在结构化工作空间中汇集运营事项。" },
      { title: "跟踪", description: "查看有助于跟踪业务的信息。" },
      { title: "决策", description: "依据应用中现有的信息作出决策。" },
    ],
    featuresTitle: "核心功能",
    featuresDescription: "DJIBEXA 汇集管理功能，具体取决于您的空间中可用的模块。",
    features: [
      { title: "销售", description: "记录并查看销售业务。" },
      { title: "库存", description: "跟踪产品和库存变动。" },
      { title: "采购", description: "组织订单和收货。" },
      { title: "客户", description: "查找客户相关信息。" },
      { title: "单据", description: "管理发票和相关单据。" },
      { title: "报表", description: "查看应用中提供的报表。" },
    ],
    operationsTitle: "组织并跟踪运营",
    operationsDescription: "共同的工作参考帮助团队查找信息并了解工作进度。",
    operations: ["按业务组织信息。", "根据用户角色和权限分配访问权。", "在应用中记录业务操作。"],
    operationsImageAlt: "汽车零件货架的示意照片",
    operationsImageCaption: "示意照片：此货架并非 DJIBEXA 应用程序的截图。",
    companiesTitle: "适应企业组织方式的解决方案",
    companiesDescription: "每家企业拥有独立管理空间，并可选择配置自己的公开展示页面。",
    companies: ["空间关联到相应企业。", "展示页面身份单独配置。", "各空间的企业信息彼此独立。"],
    approachTitle: "DJIBEXA 的理念",
    approachDescription: "如实介绍工具：实用功能、受控访问和清晰信息。",
    approachSteps: [
      { title: "实用功能", description: "介绍应用中已提供的功能。" },
      { title: "受控访问", description: "权限决定用户可访问的数据和操作。" },
      { title: "操作可追溯", description: "可按授权查看已记录的操作。" },
    ],
    faqTitle: "常见问题",
    faqDescription: "了解 DJIBEXA、管理空间以及此处介绍的功能。",
    faqs: [
      {
        question: "DJIBEXA 有什么用途？",
        answer: "DJIBEXA 是一款数字化企业管理方案，汇集销售、库存、采购、客户、单据和报表等功能。",
      },
      {
        question: "每个工作空间都提供所有功能吗？",
        answer: "可用功能取决于工作空间启用的模块以及分配给您账户的权限。",
      },
      {
        question: "企业展示页面与 DJIBEXA 是分开的吗？",
        answer: "是的。DJIBEXA 公共页面介绍解决方案。每家企业的展示页面保留自己的身份和内容。",
      },
      {
        question: "如何登录？",
        answer: "仅授权用户可以访问。请使用与账户关联的用户名或电子邮箱及密码登录。",
      },
      {
        question: "如何申请产品演示？",
        answer: "请填写本页底部的申请表。DJIBEXA 团队可能会与您联系。",
      },
    ],
    demoTitle: "申请产品演示",
    demoDescription:
      "请简要介绍您的企业和希望了解的内容。这些信息仅供 DJIBEXA 中央管理团队查看，以便跟进您的申请。",
    demoCompany: "企业名称",
    demoContactName: "您的姓名",
    demoEmail: "工作电子邮箱",
    demoPhone: "电话（可选）",
    demoMessage: "您希望了解哪些内容？",
    demoConsent: "我同意 DJIBEXA 使用这些联系方式回复我的申请。",
    demoSubmit: "提交申请",
    demoSubmitting: "正在发送…",
    demoSuccess: "申请已记录。DJIBEXA 团队可能会与您联系。",
    demoError: "申请发送失败。请检查网络连接后重试。",
    ctaTitle: "让企业管理更加清晰。",
    ctaDescription: "申请产品演示，或登录 DJIBEXA。",
    contactTitle: "了解更多 DJIBEXA 信息",
    contactDescription: "请浏览本页信息。如果您已有账户，可直接登录 DJIBEXA。",
    privacyTitle: "尊重企业空间边界",
    privacyDescription: "DJIBEXA 页面介绍解决方案，各企业展示页面和内容保持独立。",
    footerDescription: "数字化企业管理方案。",
  },
};

const FEATURE_ICONS = [Receipt, Boxes, ShoppingCart, UsersRound, ClipboardList, BarChart3];
const STEP_ICONS = [Boxes, PackageCheck, BarChart3];
const APPROACH_ICONS = [PackageCheck, ShieldCheck, ClipboardList];

export function PublicHomePage() {
  const { language, direction } = useLocale();
  const { session } = useAuth();
  const copy = HOME_COPY[language];
  const [demoForm, setDemoForm] = useState({
    companyName: "",
    contactName: "",
    email: "",
    phone: "",
    message: "",
    consent: false,
  });
  const [demoSubmitted, setDemoSubmitted] = useState(false);
  const demoRequestMutation = useMutation({
    mutationFn: () =>
      api.post("public/demo-requests/", {
        company_name: demoForm.companyName,
        contact_name: demoForm.contactName,
        email: demoForm.email,
        phone: demoForm.phone,
        message: demoForm.message,
        consent: demoForm.consent,
      }),
    onSuccess: () => {
      setDemoForm({
        companyName: "",
        contactName: "",
        email: "",
        phone: "",
        message: "",
        consent: false,
      });
      setDemoSubmitted(true);
    },
    onError: (error) => {
      toast.error(copy.demoError, {
        description: error instanceof Error ? error.message : copy.demoError,
      });
    },
  });
  const accessPath = session ? "/dashboard" : "/auth";
  const accessLabel = copy.portal;
  const navItems = [
    { href: "#accueil", label: copy.home },
    { href: "#solution", label: copy.solution },
    { href: "#fonctionnalites", label: copy.featuresNav },
    { href: "#faq", label: copy.faqNav },
    { href: "#contact", label: copy.contact },
  ];

  useEffect(() => {
    document.title = copy.title;
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = copy.description;
    const openGraphTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]');
    if (openGraphTitle) openGraphTitle.content = copy.title;
    const openGraphDescription = document.querySelector<HTMLMetaElement>(
      'meta[property="og:description"]',
    );
    if (openGraphDescription) openGraphDescription.content = copy.description;
    document.documentElement.lang = language;
    document.documentElement.dir = direction;
  }, [copy.description, copy.title, direction, language]);

  return (
    <div className="min-h-screen bg-[#F5F7FA] text-[#202B38]">
      <header className="sticky top-0 z-30 border-b border-[#DCE3EB] bg-white/95 backdrop-blur">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <a href="#accueil" aria-label="DJIBEXA — Accueil" className="flex shrink-0 items-center">
            <img src="/brand/djibexa-logo.svg" alt="DJIBEXA" className="h-8 w-28 sm:h-10 sm:w-40" />
          </a>
          <nav aria-label={copy.navLabel} className="hidden items-center gap-6 lg:flex">
            {navItems.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="text-sm font-medium text-[#425166] transition-colors hover:text-[#174A78]"
              >
                {item.label}
              </a>
            ))}
          </nav>
          <div className="hidden items-center gap-3 lg:flex">
            <LanguageSwitcher />
            <InstallAppButton />
            <Button asChild size="sm" className="bg-[#174A78] hover:bg-[#10243A]">
              <Link to={accessPath}>{accessLabel}</Link>
            </Button>
          </div>
          <div className="flex items-center gap-2 lg:hidden">
            <LanguageSwitcher />
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
                  {navItems.map((item) => (
                    <SheetClose asChild key={item.href}>
                      <a href={item.href}>{item.label}</a>
                    </SheetClose>
                  ))}
                  <SheetClose asChild>
                    <Button asChild className="bg-[#174A78] hover:bg-[#10243A]">
                      <Link to={accessPath}>{accessLabel}</Link>
                    </Button>
                  </SheetClose>
                  <div className="flex justify-start">
                    <InstallAppButton />
                  </div>
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main>
        <section
          id="accueil"
          className="overflow-hidden bg-gradient-to-br from-white via-[#F5F7FA] to-[#E7F0F9]"
        >
          <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[1fr_0.95fr] lg:px-8 lg:py-24">
            <div className="relative z-10 space-y-6">
              <p className="text-xs font-bold tracking-[0.2em] text-[#2678C8] uppercase">
                {copy.heroEyebrow}
              </p>
              <h1 className="max-w-3xl text-4xl leading-tight font-bold tracking-tight text-[#10243A] sm:text-5xl lg:text-6xl">
                {copy.heroTitle}
              </h1>
              <p className="max-w-2xl text-base leading-7 text-[#526174] sm:text-lg">
                {copy.heroDescription}
              </p>
              <div className="flex flex-col gap-3 pt-1 sm:flex-row">
                <Button asChild size="lg" className="bg-[#174A78] hover:bg-[#10243A]">
                  <a href="#solution">
                    {copy.discover}
                    <ArrowRight className="ms-2 size-4" aria-hidden="true" />
                  </a>
                </Button>
                <Button
                  asChild
                  size="lg"
                  variant="outline"
                  className="border-[#174A78] text-[#174A78]"
                >
                  <a href="#demo-request">{copy.demoAction}</a>
                </Button>
              </div>
            </div>
            <figure className="mx-auto w-full max-w-xl">
              <img
                src="/brand/djibexa-office-bright.jpeg"
                alt={copy.heroImageAlt}
                className="aspect-[3/2] h-auto w-full rounded-2xl border border-white/80 object-cover shadow-xl shadow-[#10243A]/10"
                fetchPriority="high"
              />
              <figcaption className="mt-3 text-center text-xs leading-5 text-[#718096]">
                {copy.heroImageCaption}
              </figcaption>
            </figure>
          </div>
        </section>

        <section
          id="solution"
          className="scroll-mt-20 bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-20"
        >
          <div className="mx-auto max-w-7xl">
            <div className="mx-auto max-w-3xl text-center">
              <p className="text-sm font-semibold tracking-wide text-[#2678C8] uppercase">
                DJIBEXA
              </p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.visionTitle}
              </h2>
              <p className="mt-4 leading-7 text-[#526174]">{copy.visionDescription}</p>
            </div>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
              {copy.visionSteps.map((step, index) => {
                const Icon = STEP_ICONS[index];
                if (!Icon) return null;
                return (
                  <article
                    key={step.title}
                    className="rounded-2xl border border-[#DCE3EB] bg-[#F8FAFC] p-6"
                  >
                    <span className="flex size-11 items-center justify-center rounded-xl bg-[#E7F0F9] text-[#174A78]">
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <h3 className="mt-5 text-xl font-semibold text-[#10243A]">{step.title}</h3>
                    <p className="mt-2 leading-6 text-[#526174]">{step.description}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section
          id="fonctionnalites"
          className="scroll-mt-20 border-y border-[#DCE3EB] bg-[#F5F7FA] px-4 py-16 sm:px-6 lg:px-8 lg:py-20"
        >
          <div className="mx-auto max-w-7xl">
            <div className="max-w-2xl">
              <p className="text-sm font-semibold tracking-wide text-[#2678C8] uppercase">
                DJIBEXA
              </p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.featuresTitle}
              </h2>
              <p className="mt-4 leading-7 text-[#526174]">{copy.featuresDescription}</p>
            </div>
            <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {copy.features.map((feature, index) => {
                const Icon = FEATURE_ICONS[index];
                if (!Icon) return null;
                return (
                  <article
                    key={feature.title}
                    className="flex gap-4 rounded-xl border border-[#DCE3EB] bg-white p-5 shadow-sm"
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-[#E7F0F9] text-[#174A78]">
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <div>
                      <h3 className="font-semibold text-[#10243A]">{feature.title}</h3>
                      <p className="mt-1 text-sm leading-6 text-[#526174]">{feature.description}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
          <div className="mx-auto grid max-w-7xl items-center gap-10 lg:grid-cols-2">
            <figure className="order-2 lg:order-1">
              <img
                src="/brand/djibexa-parts-shelves.jpeg"
                alt={copy.operationsImageAlt}
                className="aspect-[3/2] h-auto w-full rounded-2xl border border-[#DCE3EB] object-cover shadow-lg shadow-[#10243A]/10"
                loading="lazy"
                decoding="async"
              />
              <figcaption className="mt-3 text-xs leading-5 text-[#718096]">
                {copy.operationsImageCaption}
              </figcaption>
            </figure>
            <div className="order-1 space-y-5 lg:order-2">
              <p className="text-sm font-semibold tracking-wide text-[#2678C8] uppercase">
                DJIBEXA
              </p>
              <h2 className="text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.operationsTitle}
              </h2>
              <p className="leading-7 text-[#526174]">{copy.operationsDescription}</p>
              <ul className="space-y-3">
                {copy.operations.map((item) => (
                  <li key={item} className="flex items-start gap-3 text-[#34455A]">
                    <ShieldCheck
                      className="mt-0.5 size-5 shrink-0 text-[#2678C8]"
                      aria-hidden="true"
                    />
                    <span className="leading-6">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section className="border-y border-[#DCE3EB] bg-[#F5F7FA] px-4 py-16 sm:px-6 lg:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
            <div>
              <p className="text-sm font-semibold tracking-wide text-[#2678C8] uppercase">
                DJIBEXA
              </p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.companiesTitle}
              </h2>
              <p className="mt-4 leading-7 text-[#526174]">{copy.companiesDescription}</p>
              <div className="mt-6 rounded-xl border border-[#C7D8E8] bg-white p-5">
                <h3 className="font-semibold text-[#10243A]">{copy.privacyTitle}</h3>
                <p className="mt-2 text-sm leading-6 text-[#526174]">{copy.privacyDescription}</p>
              </div>
            </div>
            <ul className="grid gap-3">
              {copy.companies.map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 rounded-xl border border-[#DCE3EB] bg-white p-4 text-[#34455A]"
                >
                  <UsersRound className="size-5 shrink-0 text-[#174A78]" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
          <div className="mx-auto max-w-7xl">
            <div className="mx-auto max-w-3xl text-center">
              <h2 className="text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.approachTitle}
              </h2>
              <p className="mt-4 leading-7 text-[#526174]">{copy.approachDescription}</p>
            </div>
            <div className="mt-9 grid gap-4 md:grid-cols-3">
              {copy.approachSteps.map((step, index) => {
                const Icon = APPROACH_ICONS[index];
                if (!Icon) return null;
                return (
                  <article key={step.title} className="rounded-2xl border border-[#DCE3EB] p-6">
                    <Icon className="size-6 text-[#2678C8]" aria-hidden="true" />
                    <h3 className="mt-4 text-lg font-semibold text-[#10243A]">{step.title}</h3>
                    <p className="mt-2 leading-6 text-[#526174]">{step.description}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section
          id="faq"
          className="scroll-mt-20 border-y border-[#DCE3EB] bg-[#F5F7FA] px-4 py-16 sm:px-6 lg:px-8 lg:py-20"
        >
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.7fr_1.3fr]">
            <div>
              <span className="flex size-11 items-center justify-center rounded-xl bg-[#E7F0F9] text-[#174A78]">
                <CircleHelp className="size-5" aria-hidden="true" />
              </span>
              <h2 className="mt-5 text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.faqTitle}
              </h2>
              <p className="mt-4 leading-7 text-[#526174]">{copy.faqDescription}</p>
            </div>
            <div className="divide-y divide-[#DCE3EB] rounded-2xl border border-[#DCE3EB] bg-white px-5 sm:px-7">
              {copy.faqs.map((faq) => (
                <details key={faq.question} className="group py-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-[#10243A] marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2678C8] [&::-webkit-details-marker]:hidden">
                    {faq.question}
                    <span
                      aria-hidden="true"
                      className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[#E7F0F9] text-[#174A78] transition-transform group-open:rotate-45"
                    >
                      +
                    </span>
                  </summary>
                  <p className="mt-3 pe-8 leading-7 text-[#526174]">{faq.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section
          id="demo-request"
          className="scroll-mt-20 bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-20"
        >
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="max-w-xl">
              <p className="text-sm font-semibold tracking-wide text-[#2678C8] uppercase">
                DJIBEXA
              </p>
              <h2 className="mt-3 text-3xl font-bold tracking-tight text-[#10243A] sm:text-4xl">
                {copy.demoTitle}
              </h2>
              <p className="mt-4 leading-7 text-[#526174]">{copy.demoDescription}</p>
            </div>
            <form
              className="space-y-5 rounded-2xl border border-[#DCE3EB] bg-[#F8FAFC] p-5 shadow-sm sm:p-7"
              onSubmit={(event) => {
                event.preventDefault();
                setDemoSubmitted(false);
                demoRequestMutation.mutate();
              }}
            >
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="demo-company">{copy.demoCompany}</Label>
                  <Input
                    id="demo-company"
                    autoComplete="organization"
                    maxLength={200}
                    required
                    value={demoForm.companyName}
                    onChange={(event) =>
                      setDemoForm((current) => ({ ...current, companyName: event.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="demo-contact">{copy.demoContactName}</Label>
                  <Input
                    id="demo-contact"
                    autoComplete="name"
                    maxLength={150}
                    required
                    value={demoForm.contactName}
                    onChange={(event) =>
                      setDemoForm((current) => ({ ...current, contactName: event.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="demo-email">{copy.demoEmail}</Label>
                  <Input
                    id="demo-email"
                    type="email"
                    autoComplete="email"
                    maxLength={254}
                    required
                    value={demoForm.email}
                    onChange={(event) =>
                      setDemoForm((current) => ({ ...current, email: event.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="demo-phone">{copy.demoPhone}</Label>
                  <Input
                    id="demo-phone"
                    type="tel"
                    autoComplete="tel"
                    maxLength={30}
                    value={demoForm.phone}
                    onChange={(event) =>
                      setDemoForm((current) => ({ ...current, phone: event.target.value }))
                    }
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="demo-message">{copy.demoMessage}</Label>
                <Textarea
                  id="demo-message"
                  maxLength={2000}
                  minLength={10}
                  required
                  rows={4}
                  value={demoForm.message}
                  onChange={(event) =>
                    setDemoForm((current) => ({ ...current, message: event.target.value }))
                  }
                  className="border-[#C9D3DE] bg-white focus-visible:ring-[#2678C8]"
                />
              </div>
              <label className="flex items-start gap-3 text-sm leading-6 text-[#34455A]">
                <input
                  type="checkbox"
                  required
                  checked={demoForm.consent}
                  onChange={(event) =>
                    setDemoForm((current) => ({ ...current, consent: event.target.checked }))
                  }
                  className="mt-1 size-4 shrink-0 accent-[#174A78]"
                />
                <span>{copy.demoConsent}</span>
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  type="submit"
                  size="lg"
                  disabled={demoRequestMutation.isPending}
                  className="bg-[#174A78] text-white hover:bg-[#10243A]"
                >
                  {demoRequestMutation.isPending ? copy.demoSubmitting : copy.demoSubmit}
                </Button>
                {demoSubmitted && (
                  <p className="text-sm leading-6 text-emerald-800" role="status">
                    {copy.demoSuccess}
                  </p>
                )}
              </div>
            </form>
          </div>
        </section>

        <section className="bg-[#E7F0F9] px-4 py-14 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-7xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="max-w-2xl">
              <h2 className="text-3xl font-bold text-[#10243A]">{copy.ctaTitle}</h2>
              <p className="mt-3 leading-7 text-[#526174]">{copy.ctaDescription}</p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg" className="bg-[#174A78] hover:bg-[#10243A]">
                <Link to={accessPath}>{copy.portal}</Link>
              </Button>
              <Button
                asChild
                size="lg"
                variant="outline"
                className="border-[#174A78] text-[#174A78]"
              >
                <a href="#demo-request">{copy.demoAction}</a>
              </Button>
            </div>
          </div>
        </section>

        <section
          id="contact"
          className="scroll-mt-20 bg-[#10243A] px-4 py-14 text-white sm:px-6 lg:px-8"
        >
          <div className="mx-auto flex max-w-7xl flex-col gap-7 md:flex-row md:items-center md:justify-between">
            <div className="max-w-2xl">
              <p className="text-sm font-semibold tracking-wide text-[#9DC9F1] uppercase">
                DJIBEXA
              </p>
              <h2 className="mt-3 text-3xl font-bold sm:text-4xl">{copy.contactTitle}</h2>
              <p className="mt-3 leading-7 text-white/75">{copy.contactDescription}</p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg" className="bg-[#2678C8] text-white hover:bg-[#1E67AD]">
                <a href="#demo-request">{copy.demoAction}</a>
              </Button>
              <Button
                asChild
                size="lg"
                variant="outline"
                className="border-white/50 text-white hover:bg-white/10"
              >
                <Link to={accessPath}>{copy.portal}</Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-[#0B1A2A] px-4 py-8 text-white/70 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-semibold text-white">DJIBEXA</p>
            <p className="mt-1 text-sm">{copy.footerDescription}</p>
          </div>
          <nav aria-label={copy.navLabel} className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
            <a href="#solution" className="hover:text-white">
              {copy.solution}
            </a>
            <a href="#fonctionnalites" className="hover:text-white">
              {copy.featuresNav}
            </a>
            <a href="#faq" className="hover:text-white">
              {copy.faqNav}
            </a>
            <a href="#contact" className="hover:text-white">
              {copy.contact}
            </a>
            <a href="#accueil" className="hover:text-white">
              {copy.home}
            </a>
          </nav>
          <p className="text-xs">© {new Date().getFullYear()} DJIBEXA</p>
        </div>
      </footer>
    </div>
  );
}
