import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  Building2,
  Clock3,
  Globe2,
  ArrowUpRight,
  MailPlus,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  UsersRound,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLocale, type Language } from "@/lib/locale";

export const PageRoute = createFileRoute("/_authenticated/platform/")({
  head: () => ({
    meta: [
      { title: "DJIBEXA Control Center" },
      {
        name: "description",
        content: "Administration des espaces et licences DJIBEXA.",
      },
    ],
  }),
  component: PlatformOverviewPage,
});

type PlatformOverview = {
  limits: {
    maxTenants: number | null;
    maxActiveUsers: number | null;
  };
  counts: {
    tenants: number;
    activeTenants: number;
    pendingTenants: number;
    suspendedTenants: number;
    expiredTenants: number;
    activeUsers: number;
  };
  tenants: {
    id: number;
    name: string;
    slug: string;
    status: "active" | "pending" | "suspended" | "expired";
    trialEndsAt: string | null;
    trialActivatedAt: string | null;
    activeUsers: number;
    maxUsers: number;
    hasUsers: boolean;
  }[];
};

type PlatformAuditEntry = {
  id: number;
  actor: string;
  tenant: string | null;
  action: "create" | "update" | "activate" | "suspend" | "resume" | "invite_admin";
  details: Record<string, string | number | null>;
  createdAt: string;
};

const PLATFORM_COPY = {
  fr: {
    navigation: "Administration DJIBEXA",
    overview: "Vue d’ensemble",
    ownerRole: "Propriétaire de la plateforme",
    title: "Administration centrale",
    eyebrow: "Administration centrale",
    description:
      "Gérez les espaces et les licences du pilote sans consulter les données commerciales des entreprises.",
    refresh: "Actualiser",
    unavailable: "Le Control Center est indisponible",
    retry: "Réessayer",
    tenants: "Espaces créés",
    unlimitedTenants: "Sans plafond d’entreprises",
    activeTenants: "espace actif",
    activeUsers: "Utilisateurs actifs",
    noGlobalLimit: "Plafond global non configuré",
    globalLimit: "Plafond global",
    watch: "Essais à surveiller",
    pending: "à activer",
    expired: "expiré",
    suspended: "Espaces suspendus",
    suspendedDescription: "Données conservées, accès à contrôler",
    companies: "Espaces d’entreprise",
    metadata: "Métadonnées de licence et capacité uniquement.",
    spaces: "espaces",
    noSpaces: "Aucun espace configuré",
    noSpacesDescription: "Créez un espace avec le formulaire ci-dessus.",
    license: "Licence",
    statusActive: "Active",
    statusPending: "À activer",
    statusSuspended: "Suspendue",
    statusExpired: "Expirée",
    users: "Utilisateurs",
    trialEnds: "Fin de l’essai",
    confidentiality: "Confidentialité par défaut",
    confidentialityDescription:
      "Ce tableau n’affiche ni ventes, ni clients, ni factures, ni stocks détaillés.",
    webAddresses: "Adresses web en préparation",
    webAddressesDescription:
      "Le pilote utilisera un sous-domaine par entreprise après configuration du domaine, du DNS et de l’isolation serveur.",
    accessCheck: "Vérification de l’accès central…",
    loading: "Chargement du Control Center",
    unknownError: "Impossible de charger les informations de la plateforme.",
    notDefined: "Non définie",
    createSpace: "Créer un espace",
    spaceName: "Nom de l’entreprise",
    slug: "Identifiant de l’espace",
    userLimit: "Limite d’utilisateurs",
    create: "Créer l’espace",
    creating: "Création…",
    creationNote:
      "L’espace reste en attente jusqu’au démarrage de l’essai. Vous pouvez inviter son premier administrateur depuis sa fiche.",
    adminInvitation: "Inviter le premier administrateur",
    adminInvitationDescription:
      "Un mot de passe provisoire sera envoyé par e-mail et devra être changé à la première connexion. L’accès dépend de l’activation de l’espace.",
    adminUsername: "Nom d’utilisateur",
    adminEmail: "Adresse e-mail",
    adminFirstName: "Prénom",
    adminLastName: "Nom",
    sendInvitation: "Envoyer l’invitation",
    sendingInvitation: "Envoi…",
    invitationSent:
      "Invitation envoyée avec un mot de passe provisoire. Son remplacement sera obligatoire à la première connexion.",
    adminAlreadyExists: "Un compte existe déjà dans cet espace.",
    activate: "Démarrer l’essai",
    suspend: "Suspendre l’accès",
    resume: "Reprendre l’essai",
    resumeUnavailable: "Prolongation requise",
    saveLimit: "Enregistrer",
    actionError: "L’opération n’a pas pu être effectuée.",
    suspendConfirmTitle: "Suspendre cet espace ?",
    suspendConfirmDescription:
      "Ses utilisateurs ne pourront plus accéder à leur espace. Les données seront conservées.",
    activateConfirmTitle: "Démarrer la période d’essai ?",
    activateConfirmDescription:
      "La période de trois mois commencera immédiatement et l’espace deviendra accessible à ses utilisateurs.",
    cancel: "Annuler",
    confirmActivate: "Démarrer l’essai",
    confirmSuspend: "Confirmer la suspension",
    createdSuccess: "Espace créé; il est en attente d’activation.",
    capacitySaved: "Limite d’utilisateurs enregistrée.",
    activateSuccess: "Période d’essai activée pour trois mois.",
    suspendSuccess: "Accès à l’espace suspendu. Les données sont conservées.",
    resumeSuccess: "Accès à l’espace rétabli.",
    audit: "Journal des actions centrales",
    fullAudit: "Ouvrir le journal complet",
    noAudit: "Aucune action centrale enregistrée.",
    by: "par",
    audit_create: "Espace créé",
    audit_update: "Limite modifiée",
    audit_activate: "Essai activé",
    audit_suspend: "Espace suspendu",
    audit_resume: "Essai repris",
    audit_invite_admin: "Premier administrateur invité",
  },
  en: {
    navigation: "DJIBEXA administration",
    overview: "Overview",
    ownerRole: "Platform owner",
    title: "Central administration",
    eyebrow: "Central administration",
    description: "Manage pilot spaces and licenses without viewing companies’ commercial data.",
    refresh: "Refresh",
    unavailable: "Control Center is unavailable",
    retry: "Try again",
    tenants: "Spaces created",
    unlimitedTenants: "No company cap",
    activeTenants: "active space",
    activeUsers: "Active users",
    noGlobalLimit: "Global limit not configured",
    globalLimit: "Global limit",
    watch: "Trials to review",
    pending: "pending activation",
    expired: "expired",
    suspended: "Suspended spaces",
    suspendedDescription: "Data retained; access needs review",
    companies: "Company spaces",
    metadata: "License and capacity metadata only.",
    spaces: "spaces",
    noSpaces: "No spaces configured",
    noSpacesDescription: "Create a space with the form above.",
    license: "License",
    statusActive: "Active",
    statusPending: "Pending",
    statusSuspended: "Suspended",
    statusExpired: "Expired",
    users: "Users",
    trialEnds: "Trial ends",
    confidentiality: "Privacy by default",
    confidentialityDescription:
      "This dashboard shows no sales, customers, invoices, or detailed inventory.",
    webAddresses: "Web addresses are being prepared",
    webAddressesDescription:
      "The pilot will use one subdomain per company after domain, DNS, and server isolation are configured.",
    accessCheck: "Checking central access…",
    loading: "Loading Control Center",
    unknownError: "Unable to load platform information.",
    notDefined: "Not set",
    createSpace: "Create a space",
    spaceName: "Company name",
    slug: "Space identifier",
    userLimit: "User limit",
    create: "Create space",
    creating: "Creating…",
    creationNote:
      "The space remains pending until its trial starts. Invite its first administrator from its card.",
    adminInvitation: "Invite the first administrator",
    adminInvitationDescription:
      "A temporary password will be emailed and must be changed at first sign-in. Access depends on the space being active.",
    adminUsername: "Username",
    adminEmail: "Email address",
    adminFirstName: "First name",
    adminLastName: "Last name",
    sendInvitation: "Send invitation",
    sendingInvitation: "Sending…",
    invitationSent:
      "Invitation sent with a temporary password. It must be changed at first sign-in.",
    adminAlreadyExists: "An account already exists in this space.",
    activate: "Start trial",
    suspend: "Suspend access",
    resume: "Resume trial",
    resumeUnavailable: "Extension required",
    saveLimit: "Save",
    actionError: "The operation could not be completed.",
    suspendConfirmTitle: "Suspend this space?",
    suspendConfirmDescription:
      "Its users will lose access to the space. Their data will be retained.",
    activateConfirmTitle: "Start the trial?",
    activateConfirmDescription:
      "The three-month trial starts immediately and users will be able to access this space.",
    cancel: "Cancel",
    confirmActivate: "Start trial",
    confirmSuspend: "Confirm suspension",
    createdSuccess: "Space created and waiting for activation.",
    capacitySaved: "User limit saved.",
    activateSuccess: "Three-month trial activated.",
    suspendSuccess: "Space access suspended. Data is retained.",
    resumeSuccess: "Space access restored.",
    audit: "Central activity log",
    fullAudit: "Open full audit log",
    noAudit: "No central actions recorded.",
    by: "by",
    audit_create: "Space created",
    audit_update: "User limit changed",
    audit_activate: "Trial activated",
    audit_suspend: "Space suspended",
    audit_resume: "Trial resumed",
    audit_invite_admin: "First administrator invited",
  },
  ar: {
    navigation: "إدارة DJIBEXA",
    overview: "نظرة عامة",
    ownerRole: "مالك المنصة",
    title: "الإدارة المركزية",
    eyebrow: "الإدارة المركزية",
    description:
      "إدارة مساحات البرنامج التجريبي والتراخيص دون الاطلاع على البيانات التجارية للشركات.",
    refresh: "تحديث",
    unavailable: "مركز التحكم غير متاح",
    retry: "إعادة المحاولة",
    tenants: "المساحات المنشأة",
    unlimitedTenants: "دون حد للمساحات",
    activeTenants: "مساحة نشطة",
    activeUsers: "المستخدمون النشطون",
    noGlobalLimit: "الحد الإجمالي غير مضبوط",
    globalLimit: "الحد الإجمالي",
    watch: "تجارب للمراجعة",
    pending: "بانتظار التفعيل",
    expired: "منتهية",
    suspended: "مساحات معلّقة",
    suspendedDescription: "البيانات محفوظة؛ يجب مراجعة الوصول",
    companies: "مساحات الشركات",
    metadata: "بيانات الترخيص والسعة فقط.",
    spaces: "مساحات",
    noSpaces: "لا توجد مساحات مضبوطة",
    noSpacesDescription: "أنشئ مساحة باستخدام النموذج أعلاه.",
    license: "الترخيص",
    statusActive: "نشطة",
    statusPending: "بانتظار التفعيل",
    statusSuspended: "معلّقة",
    statusExpired: "منتهية",
    users: "المستخدمون",
    trialEnds: "انتهاء التجربة",
    confidentiality: "الخصوصية افتراضيًا",
    confidentialityDescription:
      "لا تعرض هذه اللوحة المبيعات أو العملاء أو الفواتير أو المخزون التفصيلي.",
    webAddresses: "عناوين الويب قيد الإعداد",
    webAddressesDescription: "سيستخدم البرنامج نطاقًا فرعيًا لكل شركة بعد إعداد DNS وعزل الخادم.",
    accessCheck: "جارٍ التحقق من الوصول المركزي…",
    loading: "جارٍ تحميل مركز التحكم",
    unknownError: "تعذر تحميل معلومات المنصة.",
    notDefined: "غير محدد",
    createSpace: "إنشاء مساحة",
    spaceName: "اسم الشركة",
    slug: "معرّف المساحة",
    userLimit: "حد المستخدمين",
    create: "إنشاء المساحة",
    creating: "جارٍ الإنشاء…",
    creationNote: "ستبقى المساحة معلّقة حتى بدء التجربة. يمكنك دعوة مديرها الأول من بطاقة المساحة.",
    adminInvitation: "دعوة المدير الأول",
    adminInvitationDescription:
      "سيُرسل رابط آمن لإعداد كلمة المرور. يظل الوصول محظورًا حتى تفعيل المساحة.",
    adminUsername: "اسم المستخدم",
    adminEmail: "البريد الإلكتروني",
    adminFirstName: "الاسم الأول",
    adminLastName: "اسم العائلة",
    sendInvitation: "إرسال الدعوة",
    sendingInvitation: "جارٍ الإرسال…",
    invitationSent: "تم إرسال الدعوة. رابط إعداد كلمة المرور للاستخدام مرة واحدة.",
    adminAlreadyExists: "يوجد حساب بالفعل في هذه المساحة.",
    activate: "بدء التجربة",
    suspend: "تعليق الوصول",
    resume: "استئناف التجربة",
    resumeUnavailable: "يلزم تمديد",
    saveLimit: "حفظ",
    actionError: "تعذر تنفيذ العملية.",
    suspendConfirmTitle: "هل تريد تعليق هذه المساحة؟",
    suspendConfirmDescription: "سيفقد مستخدموها إمكانية الوصول، مع الاحتفاظ بالبيانات.",
    activateConfirmTitle: "هل تريد بدء الفترة التجريبية؟",
    activateConfirmDescription:
      "ستبدأ الفترة لثلاثة أشهر فورًا وسيتمكن المستخدمون من الوصول إلى المساحة.",
    cancel: "إلغاء",
    confirmActivate: "بدء التجربة",
    confirmSuspend: "تأكيد التعليق",
    createdSuccess: "تم إنشاء المساحة وهي بانتظار التفعيل.",
    capacitySaved: "تم حفظ حد المستخدمين.",
    activateSuccess: "تم تفعيل فترة تجريبية لمدة ثلاثة أشهر.",
    suspendSuccess: "تم تعليق الوصول إلى المساحة مع الاحتفاظ بالبيانات.",
    resumeSuccess: "تمت استعادة الوصول إلى المساحة.",
    audit: "سجل إجراءات الإدارة المركزية",
    fullAudit: "فتح السجل الكامل",
    noAudit: "لا توجد إجراءات مركزية مسجلة.",
    by: "بواسطة",
    audit_create: "تم إنشاء المساحة",
    audit_update: "تم تغيير حد المستخدمين",
    audit_activate: "تم تفعيل التجربة",
    audit_suspend: "تم تعليق المساحة",
    audit_resume: "تم استئناف التجربة",
    audit_invite_admin: "تمت دعوة المدير الأول",
  },
  zh: {
    navigation: "DJIBEXA 平台管理",
    overview: "概览",
    ownerRole: "平台所有者",
    title: "中央管理",
    eyebrow: "中央管理",
    description: "管理试点空间和许可证，不查看企业的商业数据。",
    refresh: "刷新",
    unavailable: "控制中心不可用",
    retry: "重试",
    tenants: "已创建空间",
    unlimitedTenants: "企业数量不限",
    activeTenants: "个活跃空间",
    activeUsers: "活跃用户",
    noGlobalLimit: "尚未设置全局上限",
    globalLimit: "全局上限",
    watch: "待检查试用",
    pending: "待启用",
    expired: "已过期",
    suspended: "已暂停空间",
    suspendedDescription: "数据已保留；请检查访问状态",
    companies: "企业空间",
    metadata: "仅显示许可证和容量信息。",
    spaces: "个空间",
    noSpaces: "尚未配置空间",
    noSpacesDescription: "使用上方表单创建空间。",
    license: "许可证",
    statusActive: "启用中",
    statusPending: "待启用",
    statusSuspended: "已暂停",
    statusExpired: "已过期",
    users: "用户",
    trialEnds: "试用结束",
    confidentiality: "默认保护隐私",
    confidentialityDescription: "此面板不显示销售、客户、发票或详细库存数据。",
    webAddresses: "网址正在准备中",
    webAddressesDescription: "配置域名、DNS 和服务器隔离后，试点将为每家企业使用独立子域名。",
    accessCheck: "正在验证中央访问权限…",
    loading: "正在加载控制中心",
    unknownError: "无法加载平台信息。",
    notDefined: "未设置",
    createSpace: "创建空间",
    spaceName: "企业名称",
    slug: "空间标识",
    userLimit: "用户上限",
    create: "创建空间",
    creating: "正在创建…",
    creationNote: "空间将在试用开始前保持待启用状态。可从空间卡片邀请首位管理员。",
    adminInvitation: "邀请首位管理员",
    adminInvitationDescription: "将发送安全的密码设置链接；空间启用前无法登录。",
    adminUsername: "用户名",
    adminEmail: "电子邮箱",
    adminFirstName: "名",
    adminLastName: "姓",
    sendInvitation: "发送邀请",
    sendingInvitation: "正在发送…",
    invitationSent: "邀请已发送。密码设置链接仅可使用一次。",
    adminAlreadyExists: "此空间中已存在账户。",
    activate: "开始试用",
    suspend: "暂停访问",
    resume: "恢复试用",
    resumeUnavailable: "需要延期",
    saveLimit: "保存",
    actionError: "无法完成此操作。",
    suspendConfirmTitle: "暂停此空间？",
    suspendConfirmDescription: "该空间用户将无法访问，但数据会保留。",
    activateConfirmTitle: "开始试用？",
    activateConfirmDescription: "三个月试用期将立即开始，空间用户随后即可访问。",
    cancel: "取消",
    confirmActivate: "开始试用",
    confirmSuspend: "确认暂停",
    createdSuccess: "空间已创建，等待启用。",
    capacitySaved: "用户上限已保存。",
    activateSuccess: "已启用为期三个月的试用。",
    suspendSuccess: "空间访问已暂停，数据将保留。",
    resumeSuccess: "空间访问已恢复。",
    audit: "中央操作记录",
    fullAudit: "打开完整日志",
    noAudit: "没有中央操作记录。",
    by: "操作人",
    audit_create: "空间已创建",
    audit_update: "用户上限已更改",
    audit_activate: "试用已启用",
    audit_suspend: "空间已暂停",
    audit_resume: "试用已恢复",
    audit_invite_admin: "已邀请首位管理员",
  },
} satisfies Record<Language, Record<string, string>>;

const AUDIT_ACTION_LABELS: Record<PlatformAuditEntry["action"], keyof typeof PLATFORM_COPY.fr> = {
  create: "audit_create",
  update: "audit_update",
  activate: "audit_activate",
  suspend: "audit_suspend",
  resume: "audit_resume",
  invite_admin: "audit_invite_admin",
};

const TENANT_STATUS_LABELS: Record<
  PlatformOverview["tenants"][number]["status"],
  keyof typeof PLATFORM_COPY.fr
> = {
  active: "statusActive",
  pending: "statusPending",
  suspended: "statusSuspended",
  expired: "statusExpired",
};

const TENANT_ACTION_SUCCESS: Record<
  "activate" | "suspend" | "resume",
  keyof typeof PLATFORM_COPY.fr
> = {
  activate: "activateSuccess",
  suspend: "suspendSuccess",
  resume: "resumeSuccess",
};

function formatDate(value: string | null, language: Language) {
  if (!value) return null;
  return new Intl.DateTimeFormat(language, {
    dateStyle: "medium",
    timeZone: "Africa/Conakry",
  }).format(new Date(value));
}

function MetricCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  description: string;
  icon: typeof Building2;
}) {
  return (
    <Card className="border-border/70 shadow-sm">
      <CardContent className="flex items-start justify-between gap-4 p-5">
        <div className="space-y-2">
          <p className="text-muted-foreground text-sm font-medium">{title}</p>
          <p className="font-display text-3xl font-bold tracking-tight">{value}</p>
          <p className="text-muted-foreground text-xs">{description}</p>
        </div>
        <div className="bg-primary/10 text-primary rounded-xl p-3">
          <Icon className="size-5" aria-hidden="true" />
        </div>
      </CardContent>
    </Card>
  );
}

function PlatformOverviewPage() {
  const { isPlatformAdmin, loading: authLoading } = useAuth();
  const { language } = useLocale();
  const copy = PLATFORM_COPY[language];
  const queryClient = useQueryClient();
  const [tenantName, setTenantName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [tenantMaxUsers, setTenantMaxUsers] = useState("10");
  const [capacityDrafts, setCapacityDrafts] = useState<Record<number, string>>({});
  const [tenantActionConfirmation, setTenantActionConfirmation] = useState<{
    tenant: PlatformOverview["tenants"][number];
    action: "activate" | "suspend";
  } | null>(null);
  const overview = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => api.get<PlatformOverview>("platform/overview/"),
    enabled: !authLoading && isPlatformAdmin,
    staleTime: 30_000,
  });
  const audit = useQuery({
    queryKey: ["platform", "audit"],
    queryFn: () => api.get<{ results: PlatformAuditEntry[] }>("platform/audit/", { page_size: 25 }),
    enabled: !authLoading && isPlatformAdmin,
  });
  const refreshPlatformData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
    ]);
  };
  const createTenant = useMutation({
    mutationFn: () =>
      api.post("platform/tenants/", {
        name: tenantName.trim(),
        slug: tenantSlug.trim(),
        max_users: Number(tenantMaxUsers),
      }),
    onSuccess: async () => {
      setTenantName("");
      setTenantSlug("");
      setTenantMaxUsers("10");
      toast.success(copy.createdSuccess);
      await refreshPlatformData();
    },
    onError: (error: Error) => toast.error(copy.actionError, { description: error.message }),
  });
  const tenantAction = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "activate" | "suspend" | "resume" }) =>
      api.post(`platform/tenants/${id}/${action}/`),
    onSuccess: async (_data, variables) => {
      toast.success(copy[TENANT_ACTION_SUCCESS[variables.action]]);
      setTenantActionConfirmation(null);
      await refreshPlatformData();
    },
    onError: (error: Error) => toast.error(copy.actionError, { description: error.message }),
  });
  const updateCapacity = useMutation({
    mutationFn: ({ id, maxUsers }: { id: number; maxUsers: number }) =>
      api.patch(`platform/tenants/${id}/`, { max_users: maxUsers }),
    onSuccess: async (_data, variables) => {
      setCapacityDrafts((current) => {
        const updated = { ...current };
        delete updated[variables.id];
        return updated;
      });
      toast.success(copy.capacitySaved);
      await refreshPlatformData();
    },
    onError: (error: Error) => toast.error(copy.actionError, { description: error.message }),
  });
  const inviteTenantAdmin = useMutation({
    mutationFn: ({
      id,
      username,
      email,
      firstName,
      lastName,
    }: {
      id: number;
      username: string;
      email: string;
      firstName: string;
      lastName: string;
    }) =>
      api.post(`platform/tenants/${id}/admin-invitation/`, {
        username,
        email,
        first_name: firstName,
        last_name: lastName,
      }),
    onSuccess: async () => {
      toast.success(copy.invitationSent);
      await refreshPlatformData();
    },
    onError: (error: Error) => toast.error(copy.actionError, { description: error.message }),
  });

  if (authLoading || !isPlatformAdmin) {
    return (
      <div className="flex min-h-64 items-center justify-center" role="status">
        <span className="text-muted-foreground text-sm">{copy.accessCheck}</span>
      </div>
    );
  }

  if (overview.isPending) {
    return (
      <div className="mx-auto w-full max-w-7xl space-y-6" aria-label={copy.loading}>
        <div className="bg-muted h-28 animate-pulse rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="bg-muted h-32 animate-pulse rounded-xl" />
          ))}
        </div>
        <div className="bg-muted h-72 animate-pulse rounded-2xl" />
      </div>
    );
  }

  if (overview.isError) {
    return (
      <main className="mx-auto w-full max-w-3xl space-y-4 py-12 text-center">
        <div className="bg-destructive/10 text-destructive mx-auto flex size-12 items-center justify-center rounded-full">
          <ShieldCheck className="size-6" />
        </div>
        <h1 className="font-display text-2xl font-bold">{copy.unavailable}</h1>
        <p className="text-muted-foreground text-sm">
          {overview.error instanceof Error ? overview.error.message : copy.unknownError}
        </p>
        <Button
          variant="outline"
          disabled={overview.isFetching || audit.isFetching}
          onClick={() => {
            void Promise.all([overview.refetch(), audit.refetch()]);
          }}
        >
          <RefreshCw
            className={`mr-2 size-4 ${overview.isFetching || audit.isFetching ? "animate-spin" : ""}`}
          />
          {copy.retry}
        </Button>
      </main>
    );
  }

  const data = overview.data;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <section className="from-primary/10 via-card to-card relative overflow-hidden rounded-2xl border bg-gradient-to-br p-6 sm:p-8">
        <div className="relative z-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl space-y-3">
            <Badge variant="secondary" className="gap-1.5 px-2.5 py-1">
              <ShieldCheck className="size-3.5" />
              {copy.eyebrow}
            </Badge>
            <div className="space-y-2">
              <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
                DJIBEXA Control Center
              </h1>
              <p className="text-muted-foreground max-w-xl text-sm leading-6 sm:text-base">
                {copy.description}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            disabled={overview.isFetching || audit.isFetching}
            onClick={() => {
              void Promise.all([overview.refetch(), audit.refetch()]);
            }}
          >
            <RefreshCw
              className={`mr-2 size-4 ${overview.isFetching || audit.isFetching ? "animate-spin" : ""}`}
            />
            {copy.refresh}
          </Button>
        </div>
        <div className="bg-primary/5 pointer-events-none absolute -right-12 -top-20 size-72 rounded-full blur-3xl" />
      </section>

      <section
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Statistiques de la plateforme"
      >
        <MetricCard
          title={copy.tenants}
          value={
            data.limits.maxTenants === null
              ? data.counts.tenants
              : `${data.counts.tenants} / ${data.limits.maxTenants}`
          }
          description={
            data.limits.maxTenants === null
              ? `${data.counts.activeTenants} ${copy.activeTenants} · ${copy.unlimitedTenants}`
              : `${data.counts.activeTenants} ${copy.activeTenants}`
          }
          icon={Building2}
        />
        <MetricCard
          title={copy.activeUsers}
          value={data.counts.activeUsers}
          description={
            data.limits.maxActiveUsers === null
              ? copy.noGlobalLimit
              : `${copy.globalLimit} : ${data.limits.maxActiveUsers}`
          }
          icon={UsersRound}
        />
        <MetricCard
          title={copy.watch}
          value={data.counts.pendingTenants + data.counts.expiredTenants}
          description={`${data.counts.pendingTenants} ${copy.pending} · ${data.counts.expiredTenants} ${copy.expired}`}
          icon={Clock3}
        />
        <MetricCard
          title={copy.suspended}
          value={data.counts.suspendedTenants}
          description={copy.suspendedDescription}
          icon={ShieldCheck}
        />
      </section>

      <Card className="border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 font-display text-lg">
            <Plus className="size-4" aria-hidden="true" />
            {copy.createSpace}
          </CardTitle>
          <p className="text-muted-foreground text-sm">{copy.creationNote}</p>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[1.2fr_1fr_0.7fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              createTenant.mutate();
            }}
          >
            <label className="space-y-1.5 text-sm font-medium">
              {copy.spaceName}
              <input
                required
                maxLength={200}
                value={tenantName}
                onChange={(event) => setTenantName(event.target.value)}
                className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm outline-none focus-visible:ring-2"
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              {copy.slug}
              <input
                required
                pattern="[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*"
                maxLength={120}
                value={tenantSlug}
                onChange={(event) => setTenantSlug(event.target.value.toLowerCase())}
                className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm outline-none focus-visible:ring-2"
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              {copy.userLimit}
              <input
                required
                type="number"
                min={1}
                step={1}
                value={tenantMaxUsers}
                onChange={(event) => setTenantMaxUsers(event.target.value)}
                className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm outline-none focus-visible:ring-2"
              />
            </label>
            <div className="flex items-end">
              <Button
                type="submit"
                disabled={createTenant.isPending || !tenantName.trim() || !tenantSlug.trim()}
                className="w-full"
              >
                <Plus className="size-4" aria-hidden="true" />
                {createTenant.isPending ? copy.creating : copy.create}
              </Button>
            </div>
          </form>
          {createTenant.isError && (
            <p className="text-destructive mt-3 text-sm" role="alert">
              {createTenant.error instanceof Error ? createTenant.error.message : copy.actionError}
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="overflow-hidden border-border/70 shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between gap-3 border-b bg-muted/20 px-5 py-4 sm:px-6">
          <div>
            <CardTitle className="font-display text-lg">{copy.companies}</CardTitle>
            <p className="text-muted-foreground mt-1 text-sm">{copy.metadata}</p>
          </div>
          <Badge variant="outline">
            {data.tenants.length} {copy.spaces}
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          {data.tenants.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
              <div className="bg-muted text-muted-foreground rounded-2xl p-4">
                <Building2 className="size-7" />
              </div>
              <div className="space-y-1">
                <h2 className="font-semibold">{copy.noSpaces}</h2>
                <p className="text-muted-foreground max-w-md text-sm">{copy.noSpacesDescription}</p>
              </div>
            </div>
          ) : (
            <div className="divide-y">
              {data.tenants.map((tenant) => (
                <article
                  key={tenant.id}
                  className="grid gap-4 px-5 py-4 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,0.7fr)_minmax(0,0.7fr)_minmax(0,0.8fr)_minmax(0,1.3fr)] sm:items-center sm:px-6"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-xl">
                      <Building2 className="size-5" />
                    </div>
                    <div className="min-w-0">
                      <h2 className="truncate font-semibold">{tenant.name}</h2>
                      <p className="text-muted-foreground truncate text-xs">{tenant.slug}</p>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground text-xs">{copy.license}</p>
                    <Badge
                      variant={tenant.status === "active" ? "default" : "secondary"}
                      className="font-medium"
                    >
                      {copy[TENANT_STATUS_LABELS[tenant.status]]}
                    </Badge>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground text-xs">{copy.users}</p>
                    <form
                      className="flex items-center gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        updateCapacity.mutate({
                          id: tenant.id,
                          maxUsers: Number(capacityDrafts[tenant.id] ?? String(tenant.maxUsers)),
                        });
                      }}
                    >
                      <span className="text-sm font-medium">{tenant.activeUsers} /</span>
                      <input
                        aria-label={`${copy.userLimit}: ${tenant.name}`}
                        type="number"
                        required
                        min={Math.max(1, tenant.activeUsers)}
                        step={1}
                        value={capacityDrafts[tenant.id] ?? String(tenant.maxUsers)}
                        onChange={(event) =>
                          setCapacityDrafts((current) => ({
                            ...current,
                            [tenant.id]: event.target.value,
                          }))
                        }
                        className="border-input bg-background h-8 w-20 rounded-md border px-2 text-sm"
                      />
                      <Button
                        type="submit"
                        variant="ghost"
                        size="icon"
                        aria-label={`${copy.saveLimit}: ${tenant.name}`}
                        disabled={
                          updateCapacity.isPending ||
                          Number(capacityDrafts[tenant.id] ?? tenant.maxUsers) === tenant.maxUsers
                        }
                      >
                        <Save aria-hidden="true" />
                      </Button>
                    </form>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground text-xs">{copy.trialEnds}</p>
                    <p className="text-sm font-medium">
                      {formatDate(tenant.trialEndsAt, language) ?? copy.notDefined}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {tenant.status === "pending" && (
                      <Button
                        size="sm"
                        disabled={tenantAction.isPending}
                        onClick={() => setTenantActionConfirmation({ tenant, action: "activate" })}
                      >
                        <Play aria-hidden="true" />
                        {copy.activate}
                      </Button>
                    )}
                    {tenant.status === "active" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={tenantAction.isPending}
                        onClick={() => setTenantActionConfirmation({ tenant, action: "suspend" })}
                      >
                        <Pause aria-hidden="true" />
                        {copy.suspend}
                      </Button>
                    )}
                    {tenant.status === "suspended" &&
                      tenant.trialEndsAt &&
                      new Date(tenant.trialEndsAt).getTime() > Date.now() && (
                        <Button
                          size="sm"
                          disabled={tenantAction.isPending}
                          onClick={() => tenantAction.mutate({ id: tenant.id, action: "resume" })}
                        >
                          <Play aria-hidden="true" />
                          {copy.resume}
                        </Button>
                      )}
                    {(tenant.status === "expired" ||
                      (tenant.status === "suspended" &&
                        (!tenant.trialEndsAt ||
                          new Date(tenant.trialEndsAt).getTime() <= Date.now()))) && (
                      <Badge variant="outline">{copy.resumeUnavailable}</Badge>
                    )}
                    {tenant.hasUsers ? (
                      <span className="text-muted-foreground basis-full text-xs">
                        {copy.adminAlreadyExists}
                      </span>
                    ) : (
                      <details className="basis-full rounded-md border p-3">
                        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium">
                          <MailPlus className="size-4" aria-hidden="true" />
                          {copy.adminInvitation}
                        </summary>
                        <div className="mt-3 space-y-3">
                          <p className="text-muted-foreground text-xs">
                            {copy.adminInvitationDescription}
                          </p>
                          <form
                            className="grid gap-2 sm:grid-cols-2"
                            onSubmit={(event) => {
                              event.preventDefault();
                              const values = new FormData(event.currentTarget);
                              inviteTenantAdmin.mutate({
                                id: tenant.id,
                                username: String(values.get("username") ?? "").trim(),
                                email: String(values.get("email") ?? "").trim(),
                                firstName: String(values.get("first_name") ?? "").trim(),
                                lastName: String(values.get("last_name") ?? "").trim(),
                              });
                            }}
                          >
                            <label className="space-y-1 text-xs font-medium">
                              {copy.adminUsername}
                              <input
                                name="username"
                                required
                                maxLength={150}
                                autoComplete="username"
                                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                              />
                            </label>
                            <label className="space-y-1 text-xs font-medium">
                              {copy.adminEmail}
                              <input
                                name="email"
                                type="email"
                                required
                                maxLength={254}
                                autoComplete="email"
                                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                              />
                            </label>
                            <label className="space-y-1 text-xs font-medium">
                              {copy.adminFirstName}
                              <input
                                name="first_name"
                                maxLength={150}
                                autoComplete="given-name"
                                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                              />
                            </label>
                            <label className="space-y-1 text-xs font-medium">
                              {copy.adminLastName}
                              <input
                                name="last_name"
                                maxLength={150}
                                autoComplete="family-name"
                                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                              />
                            </label>
                            <Button
                              type="submit"
                              size="sm"
                              disabled={inviteTenantAdmin.isPending}
                              className="sm:col-span-2 sm:justify-self-start"
                            >
                              <MailPlus className="size-4" aria-hidden="true" />
                              {inviteTenantAdmin.isPending
                                ? copy.sendingInvitation
                                : copy.sendInvitation}
                            </Button>
                          </form>
                        </div>
                      </details>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 shadow-sm">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle className="font-display text-lg">{copy.audit}</CardTitle>
          <Button asChild variant="outline" size="sm">
            <Link to="/platform/$section" params={{ section: "audit" }}>
              {copy.fullAudit}
              <ArrowUpRight className="ml-2 size-4" aria-hidden="true" />
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {audit.isError ? (
            <p className="text-destructive text-sm" role="alert">
              {audit.error instanceof Error ? audit.error.message : copy.actionError}
            </p>
          ) : audit.isPending ? (
            <p className="text-muted-foreground text-sm" role="status">
              {copy.loading}
            </p>
          ) : audit.data.results.length === 0 ? (
            <p className="text-muted-foreground text-sm">{copy.noAudit}</p>
          ) : (
            <ul className="divide-y">
              {audit.data.results.slice(0, 8).map((entry) => (
                <li
                  key={entry.id}
                  className="flex flex-col gap-1 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
                >
                  <span>
                    <strong>{copy[AUDIT_ACTION_LABELS[entry.action]]}</strong>
                    {entry.tenant ? ` · ${entry.tenant}` : ""}
                    <span className="text-muted-foreground">
                      {" "}
                      {copy.by} {entry.actor}
                    </span>
                  </span>
                  <time className="text-muted-foreground text-xs">
                    {formatDate(entry.createdAt, language)}
                  </time>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <AlertDialog
        open={tenantActionConfirmation !== null}
        onOpenChange={(open) => {
          if (!open && !tenantAction.isPending) setTenantActionConfirmation(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {tenantActionConfirmation?.action === "activate"
                ? copy.activateConfirmTitle
                : copy.suspendConfirmTitle}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {tenantActionConfirmation
                ? `${tenantActionConfirmation.tenant.name} — ${
                    tenantActionConfirmation.action === "activate"
                      ? copy.activateConfirmDescription
                      : copy.suspendConfirmDescription
                  }`
                : copy.suspendConfirmDescription}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={tenantAction.isPending}>{copy.cancel}</AlertDialogCancel>
            <AlertDialogAction
              disabled={!tenantActionConfirmation || tenantAction.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (tenantActionConfirmation) {
                  tenantAction.mutate({
                    id: tenantActionConfirmation.tenant.id,
                    action: tenantActionConfirmation.action,
                  });
                }
              }}
            >
              {tenantActionConfirmation?.action === "activate"
                ? copy.confirmActivate
                : copy.confirmSuspend}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="bg-card flex gap-3 rounded-xl border p-4">
          <div className="bg-primary/10 text-primary mt-0.5 rounded-lg p-2">
            <ShieldCheck className="size-4" />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm font-semibold">{copy.confidentiality}</h2>
            <p className="text-muted-foreground text-sm leading-5">
              {copy.confidentialityDescription}
            </p>
          </div>
        </div>
        <div className="bg-card flex gap-3 rounded-xl border p-4">
          <div className="bg-primary/10 text-primary mt-0.5 rounded-lg p-2">
            <Globe2 className="size-4" />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm font-semibold">{copy.webAddresses}</h2>
            <p className="text-muted-foreground text-sm leading-5">
              {copy.webAddressesDescription}
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
