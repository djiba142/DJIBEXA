import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";

type UserStatus = "active" | "inactive" | "invitation_pending" | "locked";
type PlatformUser = {
  id: number;
  username: string;
  name: string;
  email: string;
  role: string;
  isActive: boolean;
  invitationPending: boolean;
  failedLoginAttempts: number;
  lockedUntil: string | null;
  lastLogin: string | null;
  createdAt: string;
  tenantId: number;
  tenantName: string;
};
type UserPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: PlatformUser[];
};
type PlatformSettings = {
  maxTenants: number | null;
  maxActiveUsers: number | null;
  tenantCount: number;
  activeUserCount: number;
  updatedAt: string;
};
type PlatformReports = {
  generatedAt: string;
  tenants: {
    total: number;
    active: number;
    pending: number;
    suspended: number;
    expired: number;
  };
  subscriptions: {
    total: number;
    byStatus: Record<string, number>;
  };
  confirmedPayments: { currency: string; total: string; count: number }[];
  moduleAdoption: { code: string; name: string; tenantCount: number }[];
};
type Overview = {
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
    status: string;
    trialEndsAt: string | null;
  }[];
};
type Payments = {
  payments: {
    id: number;
    tenantName: string;
    planName: string;
    amount: string;
    currency: string;
    status: string;
    paidAt: string;
  }[];
};
type Monitoring = {
  checkedAt: string;
  system: {
    database: { status: "operational" | "unavailable" };
  };
  tasks: {
    creditNotifications: {
      status: "pending" | "running" | "succeeded" | "failed" | "unavailable" | "unconfigured";
      startedAt: string | null;
      errorType: string | null;
    };
  };
};

function PageHeader({
  section,
  description,
}: {
  section: "users" | "settings" | "reports" | "security" | "incidents";
  description: string;
}) {
  const { t } = useLocale();
  return (
    <section className="from-primary/10 via-card to-card rounded-2xl border bg-gradient-to-br p-6 sm:p-8">
      <Badge variant="secondary" className="mb-3">
        {t("platform.navigation")}
      </Badge>
      <h1 className="font-display text-3xl font-bold tracking-tight">{t(`platform.${section}`)}</h1>
      <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-6">{description}</p>
    </section>
  );
}

function ErrorState({ error, retry }: { error: unknown; retry: () => void }) {
  const { t } = useLocale();
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
        <p className="text-destructive text-sm" role="alert">
          {error instanceof Error ? error.message : t("platform.section.loadError")}
        </p>
        <Button variant="outline" onClick={retry}>
          {t("platform.section.retry")}
        </Button>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card>
      <CardContent className="space-y-2 p-5">
        <p className="text-muted-foreground text-sm">{label}</p>
        <p className="font-display text-3xl font-bold">{value}</p>
        {detail && <p className="text-muted-foreground text-xs">{detail}</p>}
      </CardContent>
    </Card>
  );
}

export function PlatformUsersPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<UserStatus | "">("");
  const [page, setPage] = useState(1);
  const [confirmDeactivate, setConfirmDeactivate] = useState<number | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const users = useQuery({
    queryKey: ["platform", "users", search, filter, page],
    queryFn: () =>
      api.get<UserPage>("platform/users/", {
        search: search || undefined,
        status: filter || undefined,
        page,
        page_size: 20,
      }),
  });
  const action = useMutation({
    mutationFn: ({
      id,
      action: userAction,
    }: {
      id: number;
      action: "unlock" | "deactivate" | "activate" | "send-setup-link";
    }) => api.post<PlatformUser>(`platform/users/${id}/${userAction}/`, {}),
    onSuccess: async () => {
      setConfirmDeactivate(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "users"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
      ]);
    },
  });
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <PageHeader section="users" description={t("platform.section.description.users")} />
      {users.isError ? (
        <ErrorState error={users.error} retry={() => void users.refetch()} />
      ) : users.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{t("platform.access.usersTitle")}</CardTitle>
            <p className="text-muted-foreground text-sm">{t("platform.access.privacy")}</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_16rem]">
              <Input
                value={searchInput}
                placeholder={t("platform.access.search")}
                aria-label={t("platform.access.search")}
                onChange={(event) => {
                  setSearchInput(event.target.value);
                  setPage(1);
                }}
              />
              <select
                value={filter}
                aria-label={t("platform.access.filter")}
                onChange={(event) => {
                  setFilter(event.target.value as UserStatus | "");
                  setPage(1);
                }}
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
              >
                <option value="">{t("platform.access.allStatuses")}</option>
                <option value="active">{t("platform.access.active")}</option>
                <option value="inactive">{t("platform.access.inactive")}</option>
                <option value="invitation_pending">{t("platform.access.invitationPending")}</option>
                <option value="locked">{t("platform.access.locked")}</option>
              </select>
            </div>
            {action.isError && (
              <p className="text-destructive text-sm" role="alert">
                {action.error instanceof Error
                  ? action.error.message
                  : t("platform.access.actionError")}
              </p>
            )}
            {users.data.results.length === 0 ? (
              <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
                {t("platform.access.noUsers")}
              </p>
            ) : (
              <div className="space-y-3">
                {users.data.results.map((user) => {
                  const isLocked =
                    user.lockedUntil !== null && new Date(user.lockedUntil).getTime() > Date.now();
                  return (
                    <article key={user.id} className="space-y-3 rounded-xl border p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <h2 className="font-semibold">{user.name}</h2>
                          <p className="text-muted-foreground break-all text-sm">
                            {user.username} · {user.email || t("platform.access.noEmail")}
                          </p>
                          <p className="text-muted-foreground text-sm">
                            {user.tenantName} · {t(`platform.access.role.${user.role}`)}
                          </p>
                        </div>
                        <Badge variant={user.isActive ? "default" : "secondary"}>
                          {user.invitationPending
                            ? t("platform.access.invitationPending")
                            : user.isActive
                              ? t("platform.access.active")
                              : t("platform.access.inactive")}
                        </Badge>
                      </div>
                      <div className="text-muted-foreground flex flex-wrap gap-x-5 gap-y-1 text-xs">
                        <span>
                          {t("platform.access.lastLogin")}:{" "}
                          {user.lastLogin ? dateFormatter.format(new Date(user.lastLogin)) : "—"}
                        </span>
                        {user.failedLoginAttempts > 0 && (
                          <span>
                            {t("platform.access.failedAttempts")}: {user.failedLoginAttempts}
                          </span>
                        )}
                        {isLocked && user.lockedUntil && (
                          <span>
                            {t("platform.access.lockedUntil")}:{" "}
                            {dateFormatter.format(new Date(user.lockedUntil))}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {isLocked && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={action.isPending}
                            onClick={() => action.mutate({ id: user.id, action: "unlock" })}
                          >
                            {t("platform.access.unlock")}
                          </Button>
                        )}
                        {user.isActive && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={action.isPending}
                              onClick={() =>
                                action.mutate({ id: user.id, action: "send-setup-link" })
                              }
                            >
                              {t("platform.access.resetAccess")}
                            </Button>
                            {confirmDeactivate === user.id ? (
                              <>
                                <span className="self-center text-xs">
                                  {t("platform.access.confirmDeactivate")}
                                </span>
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    action.mutate({ id: user.id, action: "deactivate" })
                                  }
                                >
                                  {t("platform.access.confirm")}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => setConfirmDeactivate(null)}
                                >
                                  {t("platform.billing.cancelEdit")}
                                </Button>
                              </>
                            ) : (
                              <Button
                                size="sm"
                                variant="destructive"
                                disabled={action.isPending}
                                onClick={() => setConfirmDeactivate(user.id)}
                              >
                                {t("platform.access.deactivate")}
                              </Button>
                            )}
                          </>
                        )}
                        {!user.isActive && !user.invitationPending && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={action.isPending}
                            onClick={() => action.mutate({ id: user.id, action: "activate" })}
                          >
                            {t("platform.access.activate")}
                          </Button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
            <div className="flex items-center justify-between gap-3">
              <p className="text-muted-foreground text-sm">
                {t("platform.access.total")}: {users.data.count}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!users.data.previous || users.isFetching}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  {t("platform.section.auditPrevious")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!users.data.next || users.isFetching}
                  onClick={() => setPage((current) => current + 1)}
                >
                  {t("platform.section.auditNext")}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

export function PlatformSettingsPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: ["platform", "settings"],
    queryFn: () => api.get<PlatformSettings>("platform/settings/"),
  });
  const [maxTenants, setMaxTenants] = useState("");
  const [maxActiveUsers, setMaxActiveUsers] = useState("");
  useEffect(() => {
    if (settings.data) {
      setMaxTenants(settings.data.maxTenants === null ? "" : String(settings.data.maxTenants));
      setMaxActiveUsers(
        settings.data.maxActiveUsers === null ? "" : String(settings.data.maxActiveUsers),
      );
    }
  }, [settings.data]);
  const updateSettings = useMutation({
    mutationFn: () =>
      api.patch<PlatformSettings>("platform/settings/", {
        max_tenants: maxTenants === "" ? null : Number(maxTenants),
        max_active_users: maxActiveUsers === "" ? null : Number(maxActiveUsers),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "settings"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
      ]);
    },
  });

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6">
      <PageHeader section="settings" description={t("platform.section.description.settings")} />
      {settings.isError ? (
        <ErrorState error={settings.error} retry={() => void settings.refetch()} />
      ) : settings.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2">
            <Metric
              label={t("platform.settings.currentTenants")}
              value={String(settings.data.tenantCount)}
              detail={`${t("platform.settings.currentLimit")}: ${settings.data.maxTenants ?? t("platform.settings.unlimited")}`}
            />
            <Metric
              label={t("platform.settings.activeUsers")}
              value={String(settings.data.activeUserCount)}
              detail={`${t("platform.settings.currentLimit")}: ${settings.data.maxActiveUsers ?? t("platform.settings.unlimited")}`}
            />
          </section>
          <Card>
            <CardHeader>
              <CardTitle>{t("platform.settings.limitsTitle")}</CardTitle>
              <p className="text-muted-foreground text-sm">
                {t("platform.settings.limitsDescription")}
              </p>
            </CardHeader>
            <CardContent>
              <form
                className="grid gap-4 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateSettings.mutate();
                }}
              >
                <label className="space-y-1 text-sm">
                  <span>{t("platform.settings.maxTenants")}</span>
                  <Input
                    type="number"
                    min="1"
                    value={maxTenants}
                    placeholder={t("platform.settings.unlimited")}
                    onChange={(event) => setMaxTenants(event.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.settings.maxActiveUsers")}</span>
                  <Input
                    type="number"
                    min="1"
                    value={maxActiveUsers}
                    placeholder={t("platform.settings.unlimited")}
                    onChange={(event) => setMaxActiveUsers(event.target.value)}
                  />
                </label>
                <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
                  <Button disabled={updateSettings.isPending}>{t("platform.settings.save")}</Button>
                  {updateSettings.isSuccess && (
                    <p className="text-sm text-emerald-700" role="status">
                      {t("platform.settings.saved")}
                    </p>
                  )}
                  {updateSettings.isError && (
                    <p className="text-destructive text-sm" role="alert">
                      {updateSettings.error instanceof Error
                        ? updateSettings.error.message
                        : t("platform.settings.saveError")}
                    </p>
                  )}
                </div>
              </form>
            </CardContent>
          </Card>
        </>
      )}
    </main>
  );
}

export function PlatformReportsPage() {
  const { language, t } = useLocale();
  const reports = useQuery({
    queryKey: ["platform", "reports"],
    queryFn: () => api.get<PlatformReports>("platform/reports/"),
  });
  const dateFormatter = new Intl.DateTimeFormat(language, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <PageHeader section="reports" description={t("platform.section.description.reports")} />
      {reports.isError ? (
        <ErrorState error={reports.error} retry={() => void reports.refetch()} />
      ) : reports.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label={t("platform.reports.tenants")}
              value={String(reports.data.tenants.total)}
            />
            <Metric
              label={t("platform.reports.activationRate")}
              value={
                reports.data.tenants.total
                  ? `${Math.round((reports.data.tenants.active / reports.data.tenants.total) * 100)}%`
                  : "0%"
              }
              detail={`${reports.data.tenants.active} ${t("platform.reports.active")}`}
            />
            <Metric
              label={t("platform.reports.subscriptions")}
              value={String(reports.data.subscriptions.total)}
              detail={`${reports.data.subscriptions.byStatus.active ?? 0} ${t("platform.billing.status.active").toLowerCase()}`}
            />
            <Metric
              label={t("platform.reports.confirmedPayments")}
              value={String(
                reports.data.confirmedPayments.reduce((total, item) => total + item.count, 0),
              )}
              detail={t("platform.reports.paymentCount")}
            />
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>{t("platform.reports.tenantDistribution")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {(
                  [
                    ["active", reports.data.tenants.active],
                    ["pending", reports.data.tenants.pending],
                    ["suspended", reports.data.tenants.suspended],
                    ["expired", reports.data.tenants.expired],
                  ] as const
                ).map(([key, count]) => (
                  <div key={key} className="space-y-1">
                    <div className="flex justify-between gap-3 text-sm">
                      <span>{t(`platform.reports.status.${key}`)}</span>
                      <span className="font-medium">{count}</span>
                    </div>
                    <div className="bg-muted h-2 overflow-hidden rounded-full">
                      <div
                        className="bg-primary h-full rounded-full"
                        style={{
                          width: `${reports.data.tenants.total ? (count / reports.data.tenants.total) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>{t("platform.reports.confirmedPayments")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {reports.data.confirmedPayments.map((item) => (
                  <div
                    key={item.currency}
                    className="flex items-center justify-between gap-4 rounded-lg border p-3"
                  >
                    <span className="text-sm">{item.currency}</span>
                    <span className="font-semibold">
                      {new Intl.NumberFormat(language, { maximumFractionDigits: 2 }).format(
                        Number(item.total),
                      )}{" "}
                      {item.currency}
                    </span>
                  </div>
                ))}
                {reports.data.confirmedPayments.length === 0 && (
                  <p className="text-muted-foreground text-sm">
                    {t("platform.reports.noPayments")}
                  </p>
                )}
              </CardContent>
            </Card>
            <Card className="xl:col-span-2">
              <CardHeader>
                <CardTitle>{t("platform.reports.moduleAdoption")}</CardTitle>
                <p className="text-muted-foreground text-sm">
                  {t("platform.reports.moduleAdoptionDescription")}
                </p>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                {reports.data.moduleAdoption.map((module) => (
                  <div key={module.code} className="rounded-lg border p-3">
                    <div className="flex justify-between gap-3 text-sm">
                      <span>{module.name}</span>
                      <strong>{module.tenantCount}</strong>
                    </div>
                    <div className="bg-muted mt-2 h-2 overflow-hidden rounded-full">
                      <div
                        className="bg-primary h-full rounded-full"
                        style={{
                          width: `${reports.data.tenants.active ? Math.min(100, (module.tenantCount / reports.data.tenants.active) * 100) : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </section>
          <p className="text-muted-foreground text-xs">
            {t("platform.reports.generatedAt")}:{" "}
            {dateFormatter.format(new Date(reports.data.generatedAt))}
          </p>
        </>
      )}
    </main>
  );
}

export function PlatformSecurityPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const lockedUsers = useQuery({
    queryKey: ["platform", "users", "locked"],
    queryFn: () => api.get<UserPage>("platform/users/", { status: "locked", page_size: 100 }),
  });
  const unlock = useMutation({
    mutationFn: (id: number) => api.post<PlatformUser>(`platform/users/${id}/unlock/`, {}),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "users"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
      ]);
    },
  });

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <PageHeader section="security" description={t("platform.section.description.security")} />
      {lockedUsers.isError ? (
        <ErrorState error={lockedUsers.error} retry={() => void lockedUsers.refetch()} />
      ) : lockedUsers.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{t("platform.security.lockedUsers")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {unlock.isError && (
              <p className="text-destructive text-sm" role="alert">
                {unlock.error instanceof Error
                  ? unlock.error.message
                  : t("platform.access.actionError")}
              </p>
            )}
            {lockedUsers.data.results.map((user) => (
              <article
                key={user.id}
                className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="font-medium">
                    {user.name} · {user.tenantName}
                  </p>
                  <p className="text-muted-foreground text-sm">
                    {user.username} · {t("platform.access.failedAttempts")}:{" "}
                    {user.failedLoginAttempts}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={unlock.isPending}
                  onClick={() => unlock.mutate(user.id)}
                >
                  {t("platform.access.unlock")}
                </Button>
              </article>
            ))}
            {lockedUsers.data.results.length === 0 && (
              <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
                {t("platform.security.noLockedUsers")}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </main>
  );
}

export function PlatformIncidentsPage() {
  const { t } = useLocale();
  const overview = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => api.get<Overview>("platform/overview/"),
  });
  const payments = useQuery({
    queryKey: ["platform", "payments", "pending"],
    queryFn: () => api.get<Payments>("platform/payments/", { status: "pending" }),
  });
  const monitoring = useQuery({
    queryKey: ["platform", "monitoring"],
    queryFn: () => api.get<Monitoring>("platform/monitoring/"),
  });
  const failedTenants = overview.data?.tenants.filter(
    (tenant) => tenant.status === "expired" || tenant.status === "suspended",
  );
  const pendingPayments = payments.data?.payments ?? [];
  const serviceFailure =
    monitoring.data?.tasks.creditNotifications.status === "failed" ||
    monitoring.data?.system?.database?.status === "unavailable";
  const anyError = overview.isError || payments.isError || monitoring.isError;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <PageHeader section="incidents" description={t("platform.section.description.incidents")} />
      {anyError ? (
        <ErrorState
          error={overview.error ?? payments.error ?? monitoring.error}
          retry={() => {
            void overview.refetch();
            void payments.refetch();
            void monitoring.refetch();
          }}
        />
      ) : overview.isPending || payments.isPending || monitoring.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <section className="grid gap-4 md:grid-cols-2">
          {serviceFailure && (
            <AlertCard
              title={t("platform.incidents.serviceFailure")}
              description={
                monitoring.data.tasks.creditNotifications.errorType ??
                monitoring.data.tasks.creditNotifications.status
              }
              href="/platform/services"
            />
          )}
          {failedTenants?.map((tenant) => (
            <AlertCard
              key={`tenant-${tenant.id}`}
              title={`${tenant.name} · ${t(`platform.reports.status.${tenant.status}`)}`}
              description={
                tenant.trialEndsAt
                  ? `${t("platform.incidents.trialEnded")}: ${new Intl.DateTimeFormat().format(new Date(tenant.trialEndsAt))}`
                  : t("platform.incidents.accessReview")
              }
              href="/platform"
            />
          ))}
          {pendingPayments.map((payment) => (
            <AlertCard
              key={`payment-${payment.id}`}
              title={`${t("platform.incidents.paymentReview")} · ${payment.tenantName}`}
              description={`${payment.amount} ${payment.currency} · ${payment.planName} · ${payment.paidAt}`}
              href="/platform/payments"
            />
          ))}
          {!serviceFailure &&
            (failedTenants?.length ?? 0) === 0 &&
            pendingPayments.length === 0 && (
              <Card className="md:col-span-2">
                <CardContent className="text-muted-foreground p-6 text-center text-sm">
                  {t("platform.incidents.noAlerts")}
                </CardContent>
              </Card>
            )}
        </section>
      )}
    </main>
  );
}

function AlertCard({
  title,
  description,
  href,
}: {
  title: string;
  description: string;
  href: "/platform/services" | "/platform" | "/platform/payments";
}) {
  const { t } = useLocale();
  return (
    <Card className="border-amber-500/30">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
        <div className="min-w-0">
          <h2 className="font-medium">{title}</h2>
          <p className="text-muted-foreground mt-1 text-sm">{description}</p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link to={href}>{t("platform.incidents.open")}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
