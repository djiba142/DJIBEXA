import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Database, HardDrive, RefreshCw, Server } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLocale, type Language } from "@/lib/locale";

export const MonitoringRoute = createFileRoute("/_authenticated/platform/monitoring")({
  head: () => ({
    meta: [
      { title: "Surveillance — DJIBEXA Control Center" },
      { name: "description", content: "État technique mesuré de la plateforme DJIBEXA." },
    ],
  }),
  component: PlatformMonitoringPage,
});

type CheckStatus = "operational" | "unavailable" | "unconfigured";
type TaskRunStatus = "running" | "succeeded" | "failed" | "unavailable" | "unconfigured";

type TaskRun = {
  id: number;
  status: Exclude<TaskRunStatus, "unavailable" | "unconfigured">;
  startedAt: string;
  finishedAt: string | null;
  durationMs: number | null;
  errorType: string | null;
};

type MonitoringSnapshot = {
  checkedAt: string;
  system: {
    application: { status: CheckStatus };
    database: { status: CheckStatus };
    storage: {
      status: CheckStatus;
      totalBytes: number | null;
      usedBytes: number | null;
      freeBytes: number | null;
      usedPercent: number | null;
    };
  };
  tasks: {
    creditNotifications: {
      status: TaskRunStatus;
      startedAt: string | null;
      finishedAt: string | null;
      durationMs: number | null;
      errorType: string | null;
      history: TaskRun[];
    };
  };
  unconfigured: string[];
};

const MONITORING_COPY = {
  fr: {
    title: "Surveillance technique",
    description:
      "État obtenu par des vérifications actives. Les sources absentes sont signalées comme non configurées.",
    refresh: "Actualiser",
    checkedAt: "Dernière vérification",
    application: "Application",
    applicationDescription: "API de surveillance répond correctement.",
    database: "Base de données",
    databaseDescription: "Vérification de connexion et requête de contrôle.",
    storage: "Disque du serveur",
    storageDescription: "Espace du volume hébergeant l’application.",
    free: "disponibles",
    used: "utilisé",
    operational: "Opérationnel",
    unavailable: "Indisponible",
    unconfigured: "Non configuré",
    pendingTitle: "Sources de surveillance à mettre en place",
    pendingDescription: "Aucun historique ni statut n’est affiché sans source de mesure.",
    taskTitle: "Traitement des notifications WhatsApp",
    taskDescription:
      "Jusqu’aux dix dernières exécutions enregistrées. Cet historique ne confirme pas la fréquence du planificateur.",
    taskNotRun: "Aucune exécution enregistrée",
    taskRunning: "En cours",
    taskSucceeded: "Dernière exécution réussie",
    taskFailed: "Dernière exécution en échec",
    taskUnavailable: "Indisponible",
    taskDuration: "Durée",
    taskErrorType: "Type d’erreur",
    taskHistory: "Dernières exécutions enregistrées",
    taskHistoryEmpty: "Aucune exécution n’est enregistrée.",
    runSucceeded: "Réussie",
    runFailed: "Échec",
    runRunning: "En cours",
    serverErrors: "Erreurs serveur",
    applicationErrors: "Erreurs applicatives",
    backgroundTasks: "Échecs des tâches en arrière-plan",
    backups: "État des sauvegardes",
    securityAlerts: "Alertes de sécurité",
    accessCheck: "Vérification de l’accès central…",
    loading: "Chargement de la surveillance",
    unavailableTitle: "Données de surveillance indisponibles",
    unavailableDescription: "La vérification n’a pas abouti. Réessayez dans un instant.",
    retry: "Réessayer",
    unknown: "—",
  },
  en: {
    title: "Technical monitoring",
    description: "Status from active checks. Missing sources are shown as not configured.",
    refresh: "Refresh",
    checkedAt: "Last checked",
    application: "Application",
    applicationDescription: "The monitoring API is responding.",
    database: "Database",
    databaseDescription: "Connection check and health query.",
    storage: "Server disk",
    storageDescription: "Volume hosting the application.",
    free: "free",
    used: "used",
    operational: "Operational",
    unavailable: "Unavailable",
    unconfigured: "Not configured",
    pendingTitle: "Monitoring sources to configure",
    pendingDescription: "No history or status is shown without a measurement source.",
    taskTitle: "WhatsApp notification processing",
    taskDescription:
      "Up to the ten most recent recorded runs. This history does not confirm scheduler frequency.",
    taskNotRun: "No run recorded",
    taskRunning: "Running",
    taskSucceeded: "Latest run succeeded",
    taskFailed: "Latest run failed",
    taskUnavailable: "Unavailable",
    taskDuration: "Duration",
    taskErrorType: "Error type",
    taskHistory: "Recent recorded runs",
    taskHistoryEmpty: "No runs are recorded.",
    runSucceeded: "Succeeded",
    runFailed: "Failed",
    runRunning: "Running",
    serverErrors: "Server errors",
    applicationErrors: "Application errors",
    backgroundTasks: "Background task failures",
    backups: "Backup status",
    securityAlerts: "Security alerts",
    accessCheck: "Checking central access…",
    loading: "Loading monitoring",
    unavailableTitle: "Monitoring data unavailable",
    unavailableDescription: "The check did not complete. Please try again shortly.",
    retry: "Try again",
    unknown: "—",
  },
  ar: {
    title: "المراقبة التقنية",
    description: "الحالة الناتجة عن فحوصات فعلية. تظهر المصادر غير المتاحة على أنها غير مهيأة.",
    refresh: "تحديث",
    checkedAt: "آخر فحص",
    application: "التطبيق",
    applicationDescription: "واجهة المراقبة تستجيب.",
    database: "قاعدة البيانات",
    databaseDescription: "فحص الاتصال واستعلام التحقق.",
    storage: "قرص الخادم",
    storageDescription: "مساحة وحدة التخزين التي تستضيف التطبيق.",
    free: "متاح",
    used: "مستخدم",
    operational: "يعمل",
    unavailable: "غير متاح",
    unconfigured: "غير مهيأ",
    pendingTitle: "مصادر المراقبة المطلوب إعدادها",
    pendingDescription: "لا يتم عرض سجل أو حالة دون مصدر قياس.",
    taskTitle: "معالجة إشعارات واتساب",
    taskDescription: "يعرض أحدث عشرة عمليات تشغيل مسجلة كحد أقصى، ولا يؤكد ذلك وتيرة المجدول.",
    taskNotRun: "لا يوجد تشغيل مسجل",
    taskRunning: "مسجل كقيد التشغيل",
    taskSucceeded: "نجح آخر تشغيل",
    taskFailed: "فشل آخر تشغيل",
    taskUnavailable: "غير متاح",
    taskDuration: "المدة",
    taskErrorType: "نوع الخطأ",
    taskHistory: "أحدث عمليات التشغيل المسجلة",
    taskHistoryEmpty: "لا توجد عمليات تشغيل مسجلة.",
    runSucceeded: "نجاح",
    runFailed: "فشل",
    runRunning: "قيد التشغيل",
    serverErrors: "أخطاء الخادم",
    applicationErrors: "أخطاء التطبيق",
    backgroundTasks: "إخفاقات المهام الخلفية",
    backups: "حالة النسخ الاحتياطي",
    securityAlerts: "تنبيهات الأمان",
    accessCheck: "جارٍ التحقق من صلاحية الإدارة المركزية…",
    loading: "جارٍ تحميل المراقبة",
    unavailableTitle: "بيانات المراقبة غير متاحة",
    unavailableDescription: "تعذر إكمال الفحص. حاول مرة أخرى بعد قليل.",
    retry: "إعادة المحاولة",
    unknown: "—",
  },
  zh: {
    title: "技术监控",
    description: "显示主动检查的状态；未配置的数据源会明确标记。",
    refresh: "刷新",
    checkedAt: "最近检查",
    application: "应用程序",
    applicationDescription: "监控 API 正常响应。",
    database: "数据库",
    databaseDescription: "连接检查和健康查询。",
    storage: "服务器磁盘",
    storageDescription: "承载应用程序的磁盘空间。",
    free: "可用",
    used: "已使用",
    operational: "正常",
    unavailable: "不可用",
    unconfigured: "未配置",
    pendingTitle: "需要配置的监控数据源",
    pendingDescription: "没有测量来源时，不显示历史记录或状态。",
    taskTitle: "WhatsApp 通知处理",
    taskDescription: "最多显示最近十次已记录的运行；此历史记录不代表调度器运行频率。",
    taskNotRun: "没有运行记录",
    taskRunning: "运行中",
    taskSucceeded: "最近一次运行成功",
    taskFailed: "最近一次运行失败",
    taskUnavailable: "不可用",
    taskDuration: "耗时",
    taskErrorType: "错误类型",
    taskHistory: "最近记录的运行",
    taskHistoryEmpty: "没有已记录的运行。",
    runSucceeded: "成功",
    runFailed: "失败",
    runRunning: "运行中",
    serverErrors: "服务器错误",
    applicationErrors: "应用程序错误",
    backgroundTasks: "后台任务失败",
    backups: "备份状态",
    securityAlerts: "安全警报",
    accessCheck: "正在验证中央访问权限…",
    loading: "正在加载监控",
    unavailableTitle: "监控数据不可用",
    unavailableDescription: "检查未能完成，请稍后重试。",
    retry: "重试",
    unknown: "—",
  },
} satisfies Record<Language, Record<string, string>>;

type MonitoringCopyKey = keyof typeof MONITORING_COPY.fr;

const UNCONFIGURED_LABELS: Record<string, MonitoringCopyKey> = {
  serverErrors: "serverErrors",
  applicationErrors: "applicationErrors",
  backgroundTasks: "backgroundTasks",
  backups: "backups",
  securityAlerts: "securityAlerts",
};

function formatBytes(value: number | null, language: Language) {
  if (value === null) return MONITORING_COPY[language].unknown;
  return new Intl.NumberFormat(language, {
    style: "unit",
    unit: "gigabyte",
    unitDisplay: "short",
    maximumFractionDigits: 1,
  }).format(value / 1_000_000_000);
}

function StatusBadge({ status, language }: { status: CheckStatus; language: Language }) {
  const copy = MONITORING_COPY[language];
  const variant =
    status === "operational" ? "default" : status === "unavailable" ? "destructive" : "secondary";
  return <Badge variant={variant}>{copy[status]}</Badge>;
}

function PlatformMonitoringPage() {
  const { isPlatformAdmin, loading: authLoading } = useAuth();
  const { language } = useLocale();
  const copy = MONITORING_COPY[language];
  const monitoring = useQuery({
    queryKey: ["platform", "monitoring"],
    queryFn: () => api.get<MonitoringSnapshot>("platform/monitoring/"),
    enabled: !authLoading && isPlatformAdmin,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });

  if (authLoading || !isPlatformAdmin) {
    return (
      <div className="flex min-h-64 items-center justify-center" role="status">
        <span className="text-muted-foreground text-sm">{copy.accessCheck}</span>
      </div>
    );
  }

  if (monitoring.isPending) {
    return (
      <div className="mx-auto w-full max-w-7xl space-y-6" aria-label={copy.loading}>
        <div className="bg-muted h-28 animate-pulse rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="bg-muted h-36 animate-pulse rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (monitoring.isError) {
    return (
      <main className="mx-auto w-full max-w-3xl space-y-4 py-12 text-center">
        <div className="bg-destructive/10 text-destructive mx-auto flex size-12 items-center justify-center rounded-full">
          <AlertTriangle className="size-6" />
        </div>
        <h1 className="font-display text-2xl font-bold">{copy.unavailableTitle}</h1>
        <p className="text-muted-foreground text-sm">{copy.unavailableDescription}</p>
        <Button
          variant="outline"
          disabled={monitoring.isFetching}
          onClick={() => void monitoring.refetch()}
        >
          <RefreshCw className={`mr-2 size-4 ${monitoring.isFetching ? "animate-spin" : ""}`} />
          {copy.retry}
        </Button>
      </main>
    );
  }

  const snapshot = monitoring.data;
  const systemChecks = [
    {
      key: "application",
      title: copy.application,
      description: copy.applicationDescription,
      status: snapshot.system.application.status,
      icon: Server,
    },
    {
      key: "database",
      title: copy.database,
      description: copy.databaseDescription,
      status: snapshot.system.database.status,
      icon: Database,
    },
    {
      key: "storage",
      title: copy.storage,
      description: copy.storageDescription,
      status: snapshot.system.storage.status,
      icon: HardDrive,
    },
  ];
  const taskRun = snapshot.tasks.creditNotifications;
  const taskLabel = {
    running: copy.taskRunning,
    succeeded: copy.taskSucceeded,
    failed: copy.taskFailed,
    unavailable: copy.taskUnavailable,
    unconfigured: copy.taskNotRun,
  }[taskRun.status];
  const taskVariant =
    taskRun.status === "failed"
      ? "destructive"
      : taskRun.status === "unconfigured" || taskRun.status === "unavailable"
        ? "secondary"
        : "default";

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <section className="from-primary/10 via-card to-card relative overflow-hidden rounded-2xl border bg-gradient-to-br p-6 sm:p-8">
        <div className="relative z-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl space-y-3">
            <Badge variant="secondary" className="gap-1.5 px-2.5 py-1">
              <Activity className="size-3.5" />
              {copy.title}
            </Badge>
            <div className="space-y-2">
              <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
                {copy.title}
              </h1>
              <p className="text-muted-foreground max-w-xl text-sm leading-6 sm:text-base">
                {copy.description}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground text-xs">
              {copy.checkedAt}:{" "}
              {new Intl.DateTimeFormat(language, {
                dateStyle: "medium",
                timeStyle: "short",
                timeZone: "Africa/Conakry",
              }).format(new Date(snapshot.checkedAt))}
            </p>
            <Button
              variant="outline"
              disabled={monitoring.isFetching}
              onClick={() => void monitoring.refetch()}
            >
              <RefreshCw className={`mr-2 size-4 ${monitoring.isFetching ? "animate-spin" : ""}`} />
              {copy.refresh}
            </Button>
          </div>
        </div>
        <div className="bg-primary/5 pointer-events-none absolute -right-12 -top-20 size-72 rounded-full blur-3xl" />
      </section>

      <section className="grid gap-4 md:grid-cols-3" aria-label={copy.title}>
        {systemChecks.map((check) => {
          const Icon = check.icon;
          const storage = check.key === "storage" ? snapshot.system.storage : null;
          return (
            <Card key={check.key} className="border-border/70 shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
                <div className="space-y-2">
                  <CardTitle className="font-display text-lg">{check.title}</CardTitle>
                  <StatusBadge status={check.status} language={language} />
                </div>
                <div className="bg-primary/10 text-primary rounded-xl p-3">
                  <Icon className="size-5" aria-hidden="true" />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-muted-foreground text-sm">{check.description}</p>
                {storage && storage.status === "operational" && (
                  <div className="space-y-2">
                    <div className="flex justify-between gap-3 text-sm">
                      <span>
                        {formatBytes(storage.freeBytes, language)} {copy.free}
                      </span>
                      <span className="text-muted-foreground">
                        {storage.usedPercent === null
                          ? copy.unknown
                          : `${storage.usedPercent}% ${copy.used}`}
                      </span>
                    </div>
                    <div
                      className="bg-muted h-2 overflow-hidden rounded-full"
                      role="progressbar"
                      aria-valuenow={storage.usedPercent ?? 0}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={copy.storage}
                    >
                      <div
                        className="bg-primary h-full rounded-full transition-[width]"
                        style={{ width: `${storage.usedPercent ?? 0}%` }}
                      />
                    </div>
                    <p className="text-muted-foreground text-xs">
                      {formatBytes(storage.usedBytes, language)} /{" "}
                      {formatBytes(storage.totalBytes, language)}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </section>

      <Card className="border-border/70 shadow-sm">
        <CardHeader>
          <CardTitle className="font-display text-lg">{copy.taskTitle}</CardTitle>
          <p className="text-muted-foreground text-sm">{copy.taskDescription}</p>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={taskVariant}>{taskLabel}</Badge>
            {taskRun.startedAt && (
              <span className="text-muted-foreground text-sm">
                {new Intl.DateTimeFormat(language, {
                  dateStyle: "medium",
                  timeStyle: "short",
                  timeZone: "Africa/Conakry",
                }).format(new Date(taskRun.startedAt))}
              </span>
            )}
            {taskRun.durationMs !== null && (
              <span className="text-muted-foreground text-sm">
                {copy.taskDuration}: {taskRun.durationMs} ms
              </span>
            )}
            {taskRun.errorType && (
              <span className="text-destructive text-sm">
                {copy.taskErrorType}: {taskRun.errorType}
              </span>
            )}
          </div>
          {taskRun.history.length > 0 && (
            <section className="space-y-2" aria-label={copy.taskHistory}>
              <h2 className="text-sm font-semibold">{copy.taskHistory}</h2>
              <ul className="divide-y rounded-lg border">
                {taskRun.history.map((run) => (
                  <li
                    key={run.id}
                    className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-3">
                      <Badge variant={run.status === "failed" ? "destructive" : "secondary"}>
                        {run.status === "failed"
                          ? copy.runFailed
                          : run.status === "succeeded"
                            ? copy.runSucceeded
                            : copy.runRunning}
                      </Badge>
                      <time className="text-muted-foreground text-xs">
                        {new Intl.DateTimeFormat(language, {
                          dateStyle: "medium",
                          timeStyle: "short",
                          timeZone: "Africa/Conakry",
                        }).format(new Date(run.startedAt))}
                      </time>
                      {run.durationMs !== null && (
                        <span className="text-muted-foreground text-xs">{run.durationMs} ms</span>
                      )}
                    </div>
                    {run.errorType && (
                      <span className="text-destructive text-xs">
                        {copy.taskErrorType}: {run.errorType}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {taskRun.status === "unconfigured" && (
            <p className="text-muted-foreground text-sm">{copy.taskHistoryEmpty}</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 shadow-sm">
        <CardHeader>
          <CardTitle className="font-display text-lg">{copy.pendingTitle}</CardTitle>
          <p className="text-muted-foreground text-sm">{copy.pendingDescription}</p>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {snapshot.unconfigured.map((key) => {
              const labelKey = UNCONFIGURED_LABELS[key];
              return (
                <li
                  key={key}
                  className="bg-muted/40 flex items-center justify-between gap-3 rounded-lg border p-3"
                >
                  <span className="text-sm font-medium">{labelKey ? copy[labelKey] : key}</span>
                  <StatusBadge status="unconfigured" language={language} />
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </main>
  );
}
