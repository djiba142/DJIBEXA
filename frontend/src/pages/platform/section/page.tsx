import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Activity, ArrowUpRight, CheckCircle2, Clock3, Search, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import {
  PlatformModulesPage,
  PlatformDomainsPage,
  PlatformPaymentsPage,
  PlatformPlansPage,
} from "@/pages/platform/management";
import {
  PlatformIncidentsPage,
  PlatformReportsPage,
  PlatformSecurityPage,
  PlatformSettingsPage,
  PlatformUsersPage,
} from "@/pages/platform/operations";

type SectionKey =
  | "services"
  | "incidents"
  | "security"
  | "backups"
  | "maintenance"
  | "plans"
  | "payments"
  | "modules"
  | "users"
  | "domains"
  | "reports"
  | "settings"
  | "support"
  | "resources"
  | "audit";

type CheckStatus = "operational" | "unavailable" | "unconfigured";

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
};

type PlatformOverview = {
  counts: {
    activeTenants: number;
    activeUsers: number;
  };
};

type AuditEntry = {
  id: number;
  actor: string;
  tenant: string | null;
  action: string;
  details: Record<string, string | number | null>;
  createdAt: string;
};

type AuditPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: AuditEntry[];
};

type DemoRequestStatus = "new" | "contacted" | "closed";
const DEMO_REQUEST_STATUSES: DemoRequestStatus[] = ["new", "contacted", "closed"];

function isDemoRequestStatus(value: string): value is DemoRequestStatus {
  return DEMO_REQUEST_STATUSES.some((status) => status === value);
}

type DemoRequest = {
  id: number;
  companyName: string;
  contactName: string;
  email: string;
  phone: string;
  message: string;
  status: DemoRequestStatus;
  createdAt: string;
  updatedAt: string;
};

type DemoRequestPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: DemoRequest[];
};

const SECTION_KEYS: SectionKey[] = [
  "services",
  "incidents",
  "security",
  "backups",
  "maintenance",
  "plans",
  "payments",
  "modules",
  "users",
  "domains",
  "reports",
  "settings",
  "support",
  "resources",
  "audit",
];

const AUDIT_ACTION_LABELS: Record<string, string> = {
  create: "audit_create",
  update: "audit_update",
  activate: "audit_activate",
  suspend: "audit_suspend",
  resume: "audit_resume",
  invite_admin: "audit_invite_admin",
  plan_create: "audit_plan_create",
  plan_update: "audit_plan_update",
  subscription_assign: "audit_subscription_assign",
  subscription_cancel: "audit_subscription_cancel",
  payment_record: "audit_payment_record",
  payment_confirm: "audit_payment_confirm",
  payment_reject: "audit_payment_reject",
  module_override: "audit_module_override",
  user_access: "audit_user_access",
  settings_update: "audit_settings_update",
};

const AUDIT_DETAIL_LABELS: Record<string, string> = {
  name: "name",
  slug: "slug",
  max_users: "maxUsers",
  status: "status",
  field: "field",
  old_value: "oldValue",
  new_value: "newValue",
  trial_ends_at: "trialEndsAt",
  role: "role",
  plan_id: "planId",
  plan_name: "planName",
  amount: "amount",
  currency: "currency",
  module_code: "moduleCode",
  user_id: "userId",
  username: "username",
  old_max_tenants: "oldMaxTenants",
  new_max_tenants: "newMaxTenants",
  old_max_active_users: "oldMaxActiveUsers",
  new_max_active_users: "newMaxActiveUsers",
  action: "action",
};

const AUDIT_DETAIL_ACTION_LABELS: Record<string, string> = {
  unlock: "unlock",
  deactivate: "deactivate",
  activate_user: "activate",
  send_setup_link: "sendSetupLink",
  setup_email_failed: "setupEmailFailed",
};

export function PlatformSectionPage({ section }: { section: string }) {
  const { language, t } = useLocale();
  const queryClient = useQueryClient();
  const [auditSearchInput, setAuditSearchInput] = useState("");
  const [auditSearch, setAuditSearch] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditPage, setAuditPage] = useState(1);
  const [demoSearchInput, setDemoSearchInput] = useState("");
  const [demoSearch, setDemoSearch] = useState("");
  const [demoStatus, setDemoStatus] = useState("");
  const [demoPage, setDemoPage] = useState(1);
  useEffect(() => {
    const timeout = window.setTimeout(() => setAuditSearch(auditSearchInput.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [auditSearchInput]);
  useEffect(() => {
    const timeout = window.setTimeout(() => setDemoSearch(demoSearchInput.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [demoSearchInput]);

  const isKnownSection = SECTION_KEYS.includes(section as SectionKey);
  const currentSection = isKnownSection ? (section as SectionKey) : null;
  const showsHealth = currentSection === "services" || currentSection === "resources";
  const monitoring = useQuery({
    queryKey: ["platform", "monitoring"],
    queryFn: () => api.get<MonitoringSnapshot>("platform/monitoring/"),
    enabled: showsHealth,
    staleTime: 30_000,
  });
  const overview = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => api.get<PlatformOverview>("platform/overview/"),
    enabled: currentSection === "resources",
    staleTime: 30_000,
  });
  const audit = useQuery({
    queryKey: ["platform", "audit", auditSearch, auditAction, auditPage],
    queryFn: () =>
      api.get<AuditPage>("platform/audit/", {
        search: auditSearch || undefined,
        action: auditAction || undefined,
        page: auditPage,
        page_size: 20,
      }),
    enabled: currentSection === "audit",
    staleTime: 30_000,
  });
  const demoRequests = useQuery({
    queryKey: ["platform", "demo-requests", demoSearch, demoStatus, demoPage],
    queryFn: () =>
      api.get<DemoRequestPage>("platform/demo-requests/", {
        search: demoSearch || undefined,
        status: demoStatus || undefined,
        page: demoPage,
        page_size: 20,
      }),
    enabled: currentSection === "support",
    staleTime: 30_000,
  });
  const updateDemoRequest = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DemoRequestStatus }) =>
      api.patch<{ id: number; status: DemoRequestStatus }>(`platform/demo-requests/${id}/`, {
        status,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["platform", "demo-requests"] }),
  });

  if (!currentSection) {
    return (
      <main className="mx-auto w-full max-w-3xl py-12 text-center">
        <h1 className="font-display text-2xl font-bold">Section introuvable</h1>
      </main>
    );
  }
  if (currentSection === "plans") return <PlatformPlansPage />;
  if (currentSection === "payments") return <PlatformPaymentsPage />;
  if (currentSection === "modules") return <PlatformModulesPage />;
  if (currentSection === "domains") return <PlatformDomainsPage />;
  if (currentSection === "users") return <PlatformUsersPage />;
  if (currentSection === "settings") return <PlatformSettingsPage />;
  if (currentSection === "reports") return <PlatformReportsPage />;
  if (currentSection === "security") return <PlatformSecurityPage />;
  if (currentSection === "incidents") return <PlatformIncidentsPage />;

  const title = t(`platform.${currentSection}`);
  const description = t(`platform.section.description.${currentSection}`);
  const sectionDataError =
    monitoring.isError || (currentSection === "resources" && overview.isError);
  const dateFormatter = new Intl.DateTimeFormat(language, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Africa/Conakry",
  });

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <section className="from-primary/10 via-card to-card relative overflow-hidden rounded-2xl border bg-gradient-to-br p-6 sm:p-8">
        <div className="relative z-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl space-y-3">
            <Badge variant="secondary" className="gap-1.5 px-2.5 py-1">
              <Activity className="size-3.5" />
              {t("platform.navigation")}
            </Badge>
            <div className="space-y-2">
              <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
                {title}
              </h1>
              <p className="text-muted-foreground max-w-2xl text-sm leading-6 sm:text-base">
                {description}
              </p>
            </div>
          </div>
          {(showsHealth || currentSection === "audit") && (
            <Button asChild variant="outline">
              <Link to={currentSection === "audit" ? "/platform" : "/platform/monitoring"}>
                {currentSection === "audit"
                  ? t("platform.section.openOverview")
                  : t("platform.section.openMonitoring")}
                <ArrowUpRight className="ml-2 size-4" />
              </Link>
            </Button>
          )}
        </div>
        <div className="bg-primary/5 pointer-events-none absolute -right-12 -top-20 size-72 rounded-full blur-3xl" />
      </section>

      {(currentSection === "services" || currentSection === "resources") && (
        <section className="space-y-4">
          {monitoring.isPending || (currentSection === "resources" && overview.isPending) ? (
            <div className="bg-muted h-40 animate-pulse rounded-xl" />
          ) : sectionDataError ? (
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
                <p className="text-destructive flex items-center gap-2 text-sm" role="alert">
                  <ShieldAlert className="size-4" />
                  {t("platform.section.loadError")}
                </p>
                <Button
                  variant="outline"
                  disabled={monitoring.isFetching || overview.isFetching}
                  onClick={() => {
                    void monitoring.refetch();
                    if (currentSection === "resources") void overview.refetch();
                  }}
                >
                  {t("platform.section.retry")}
                </Button>
              </CardContent>
            </Card>
          ) : (
            <>
              {currentSection === "services" && (
                <section className="grid gap-4 md:grid-cols-3" aria-label={title}>
                  {(
                    [
                      ["application", monitoring.data.system.application.status],
                      ["database", monitoring.data.system.database.status],
                      ["storage", monitoring.data.system.storage.status],
                    ] as const
                  ).map(([key, checkStatus]) => (
                    <Card key={key}>
                      <CardHeader className="flex flex-row items-center justify-between gap-3">
                        <CardTitle className="font-display text-base">
                          {t(`platform.section.${key}`)}
                        </CardTitle>
                        <Badge variant={checkStatus === "operational" ? "default" : "destructive"}>
                          {t(`platform.monitoring.status.${checkStatus}`)}
                        </Badge>
                      </CardHeader>
                      {key === "storage" && checkStatus === "operational" && (
                        <CardContent className="text-muted-foreground text-sm">
                          {monitoring.data.system.storage.usedPercent === null
                            ? t("platform.monitoring.unknown")
                            : `${monitoring.data.system.storage.usedPercent}%`}
                        </CardContent>
                      )}
                    </Card>
                  ))}
                </section>
              )}
              {currentSection === "resources" && (
                <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  <MetricCard
                    title={t("platform.section.activeSpaces")}
                    value={overview.data ? String(overview.data.counts.activeTenants) : "—"}
                    description={t("platform.section.measurementNote")}
                  />
                  <MetricCard
                    title={t("platform.section.activeUsers")}
                    value={overview.data ? String(overview.data.counts.activeUsers) : "—"}
                    description={t("platform.section.measurementNote")}
                  />
                  <MetricCard
                    title={t("platform.section.storage")}
                    value={
                      monitoring.data.system.storage.usedPercent === null
                        ? "—"
                        : `${monitoring.data.system.storage.usedPercent}%`
                    }
                    description={t("platform.section.measurementNote")}
                  />
                </section>
              )}
              <p className="text-muted-foreground flex items-center gap-2 text-xs">
                <Clock3 className="size-3.5" />
                {t("platform.section.lastChecked")}:{" "}
                {dateFormatter.format(new Date(monitoring.data.checkedAt))}
              </p>
            </>
          )}
        </section>
      )}

      {currentSection === "audit" && (
        <Card className="border-border/70 shadow-sm">
          <CardHeader>
            <CardTitle className="font-display text-lg">
              {t("platform.section.auditTitle")}
            </CardTitle>
            <p className="text-muted-foreground text-sm">{t("platform.section.auditPrivacy")}</p>
          </CardHeader>
          <CardContent>
            <div className="mb-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
              <label className="relative">
                <span className="sr-only">{t("platform.section.auditSearch")}</span>
                <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
                <Input
                  value={auditSearchInput}
                  onChange={(event) => {
                    setAuditSearchInput(event.target.value);
                    setAuditPage(1);
                  }}
                  placeholder={t("platform.section.auditSearch")}
                  className="pl-9"
                />
              </label>
              <label className="space-y-1">
                <span className="sr-only">{t("platform.section.auditActionFilter")}</span>
                <select
                  value={auditAction}
                  onChange={(event) => {
                    setAuditAction(event.target.value);
                    setAuditPage(1);
                  }}
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                >
                  <option value="">{t("platform.section.auditAllActions")}</option>
                  {Object.keys(AUDIT_ACTION_LABELS).map((action) => (
                    <option key={action} value={action}>
                      {t(`platform.auditAction.${AUDIT_ACTION_LABELS[action]}`)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {audit.isError ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-destructive text-sm" role="alert">
                  {t("platform.section.loadError")}
                </p>
                <Button
                  variant="outline"
                  disabled={audit.isFetching}
                  onClick={() => void audit.refetch()}
                >
                  {t("platform.section.retry")}
                </Button>
              </div>
            ) : audit.isPending ? (
              <div className="bg-muted h-24 animate-pulse rounded-lg" />
            ) : audit.data.results.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                {auditSearch || auditAction
                  ? t("platform.section.auditNoMatches")
                  : t("platform.section.noAudit")}
              </p>
            ) : (
              <>
                <ul className="divide-y">
                  {audit.data.results.map((entry) => (
                    <li
                      key={entry.id}
                      className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
                    >
                      <div className="min-w-0 flex-1 space-y-1">
                        <p>
                          <strong>
                            {t(
                              `platform.auditAction.${AUDIT_ACTION_LABELS[entry.action] ?? "unknown"}`,
                            )}
                          </strong>
                          {entry.tenant ? ` · ${entry.tenant}` : ""}
                          <span className="text-muted-foreground">
                            {" "}
                            · {t("platform.section.by")} {entry.actor}
                          </span>
                        </p>
                        {Object.entries(entry.details).some(([key]) =>
                          Object.hasOwn(AUDIT_DETAIL_LABELS, key),
                        ) && (
                          <details className="text-muted-foreground text-xs">
                            <summary className="w-fit cursor-pointer">
                              {t("platform.section.auditDetails")}
                            </summary>
                            <dl className="mt-2 grid gap-x-3 gap-y-1 pl-4 sm:grid-cols-[auto_1fr]">
                              {Object.entries(entry.details)
                                .filter(([key]) => Object.hasOwn(AUDIT_DETAIL_LABELS, key))
                                .map(([key, value]) => {
                                  let displayValue = value === null ? "—" : String(value);
                                  if (key === "status" && typeof value === "string") {
                                    displayValue = t(`platform.auditStatus.${value}`);
                                  } else if (key === "field" && typeof value === "string") {
                                    displayValue = t(`platform.auditDetailValue.${value}`);
                                  } else if (key === "trial_ends_at" && typeof value === "string") {
                                    const trialEnd = new Date(value);
                                    if (!Number.isNaN(trialEnd.getTime())) {
                                      displayValue = dateFormatter.format(trialEnd);
                                    }
                                  } else if (
                                    key === "action" &&
                                    typeof value === "string" &&
                                    AUDIT_DETAIL_ACTION_LABELS[value]
                                  ) {
                                    displayValue = t(
                                      `platform.auditDetailAction.${AUDIT_DETAIL_ACTION_LABELS[value]}`,
                                    );
                                  }
                                  return (
                                    <div key={key} className="contents">
                                      <dt>
                                        {t(`platform.auditDetail.${AUDIT_DETAIL_LABELS[key]}`)}
                                      </dt>
                                      <dd className="break-all text-foreground">{displayValue}</dd>
                                    </div>
                                  );
                                })}
                            </dl>
                          </details>
                        )}
                      </div>
                      <time className="text-muted-foreground shrink-0 text-xs">
                        {dateFormatter.format(new Date(entry.createdAt))}
                      </time>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-muted-foreground text-xs" aria-live="polite">
                    {t("platform.section.auditShowing")} {(auditPage - 1) * 20 + 1}–
                    {(auditPage - 1) * 20 + audit.data.results.length} / {audit.data.count}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!audit.data.previous || audit.isFetching}
                      onClick={() => setAuditPage((current) => Math.max(1, current - 1))}
                    >
                      {t("platform.section.auditPrevious")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!audit.data.next || audit.isFetching}
                      onClick={() => setAuditPage((current) => current + 1)}
                    >
                      {t("platform.section.auditNext")}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {currentSection === "support" && (
        <Card className="border-border/70 shadow-sm">
          <CardHeader className="space-y-4">
            <div className="space-y-2">
              <CardTitle className="font-display text-lg">
                {t("platform.section.supportTitle")}
              </CardTitle>
              <p className="text-muted-foreground text-sm">
                {t("platform.section.supportPrivacy")}
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
              <Input
                type="search"
                value={demoSearchInput}
                placeholder={t("platform.section.supportSearch")}
                aria-label={t("platform.section.supportSearch")}
                onChange={(event) => {
                  setDemoSearchInput(event.target.value);
                  setDemoPage(1);
                }}
              />
              <select
                value={demoStatus}
                aria-label={t("platform.section.supportFilter")}
                onChange={(event) => {
                  setDemoStatus(event.target.value);
                  setDemoPage(1);
                }}
                className="border-input bg-background ring-offset-background focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              >
                <option value="">{t("platform.section.supportAllStatuses")}</option>
                <option value="new">{t("platform.section.supportStatusNew")}</option>
                <option value="contacted">{t("platform.section.supportStatusContacted")}</option>
                <option value="closed">{t("platform.section.supportStatusClosed")}</option>
              </select>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {demoRequests.isPending ? (
              <div className="bg-muted h-32 animate-pulse rounded-xl" />
            ) : demoRequests.isError ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 p-4">
                <p className="text-destructive flex items-center gap-2 text-sm" role="alert">
                  <ShieldAlert className="size-4" />
                  {t("platform.section.supportLoadError")}
                </p>
                <Button
                  variant="outline"
                  disabled={demoRequests.isFetching}
                  onClick={() => void demoRequests.refetch()}
                >
                  {t("platform.section.retry")}
                </Button>
              </div>
            ) : (
              <>
                <p className="text-muted-foreground text-sm">
                  {t("platform.section.supportShowing")}: {demoRequests.data.count}
                </p>
                {updateDemoRequest.isError && (
                  <p className="text-destructive text-sm" role="alert">
                    {t("platform.section.supportUpdateError")}
                  </p>
                )}
                {demoRequests.data.results.length === 0 ? (
                  <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
                    {t("platform.section.supportNoRequests")}
                  </p>
                ) : (
                  <div className="space-y-4">
                    {demoRequests.data.results.map((request) => (
                      <article
                        key={request.id}
                        className="space-y-4 rounded-xl border border-border/70 p-4 sm:p-5"
                      >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div className="space-y-1">
                            <h2 className="font-semibold text-foreground">{request.companyName}</h2>
                            <p className="text-muted-foreground text-xs">
                              {t("platform.section.supportCreated")}:{" "}
                              {dateFormatter.format(new Date(request.createdAt))}
                            </p>
                          </div>
                          <select
                            value={request.status}
                            aria-label={`${t("platform.section.supportStatusLabel")}: ${request.companyName}`}
                            disabled={updateDemoRequest.isPending}
                            onChange={(event) => {
                              const status = event.target.value;
                              if (isDemoRequestStatus(status)) {
                                updateDemoRequest.mutate({ id: request.id, status });
                              }
                            }}
                            className="border-input bg-background ring-offset-background focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 sm:w-48"
                          >
                            <option value="new">{t("platform.section.supportStatusNew")}</option>
                            <option value="contacted">
                              {t("platform.section.supportStatusContacted")}
                            </option>
                            <option value="closed">
                              {t("platform.section.supportStatusClosed")}
                            </option>
                          </select>
                        </div>
                        <dl className="grid gap-3 text-sm sm:grid-cols-2">
                          <div>
                            <dt className="text-muted-foreground">
                              {t("platform.section.supportContact")}
                            </dt>
                            <dd className="font-medium">{request.contactName}</dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">
                              {t("platform.section.supportEmail")}
                            </dt>
                            <dd>
                              <a
                                className="text-primary break-all underline-offset-4 hover:underline"
                                href={`mailto:${request.email}`}
                              >
                                {request.email}
                              </a>
                            </dd>
                          </div>
                          {request.phone && (
                            <div>
                              <dt className="text-muted-foreground">
                                {t("platform.section.supportPhone")}
                              </dt>
                              <dd>
                                <a
                                  className="text-primary underline-offset-4 hover:underline"
                                  href={`tel:${request.phone}`}
                                >
                                  {request.phone}
                                </a>
                              </dd>
                            </div>
                          )}
                        </dl>
                        <div className="space-y-1 border-t pt-3">
                          <h3 className="text-muted-foreground text-sm font-medium">
                            {t("platform.section.supportMessage")}
                          </h3>
                          <p className="whitespace-pre-wrap break-words text-sm leading-6">
                            {request.message}
                          </p>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!demoRequests.data.previous || demoRequests.isFetching}
                    onClick={() => setDemoPage((current) => Math.max(1, current - 1))}
                  >
                    {t("platform.section.auditPrevious")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!demoRequests.data.next || demoRequests.isFetching}
                    onClick={() => setDemoPage((current) => current + 1)}
                  >
                    {t("platform.section.auditNext")}
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {!["services", "resources", "audit", "support"].includes(currentSection) && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-start gap-3 p-6 sm:flex-row sm:items-center">
            <div className="bg-muted rounded-xl p-3">
              <ShieldAlert className="text-muted-foreground size-5" />
            </div>
            <div className="space-y-1">
              <h2 className="font-semibold">{t("platform.section.notConfigured")}</h2>
              <p className="text-muted-foreground text-sm">
                {t("platform.section.measurementNote")}
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

function MetricCard({
  title,
  value,
  description,
}: {
  title: string;
  value: string;
  description: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-muted-foreground text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-display text-2xl font-bold">{value}</p>
        <p className="text-muted-foreground mt-2 text-xs">{description}</p>
      </CardContent>
    </Card>
  );
}
