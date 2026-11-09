import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";

type Module = {
  id: number;
  code: string;
  name: string;
  description: string;
  dependencies: string[];
  sortOrder: number;
  isActive: boolean;
};

type Plan = {
  id: number;
  code: string;
  name: string;
  description: string;
  price: string;
  currency: string;
  billingPeriod: string;
  durationMonths: number;
  maxUsers: number;
  modules: string[];
  isActive: boolean;
};

type Tenant = {
  id: number;
  name: string;
  slug: string;
  status: string;
};

type Subscription = {
  id: number;
  tenantId: number;
  tenantName: string;
  planId: number;
  planName: string;
  status: string;
  amount: string;
  currency: string;
  durationMonths: number;
  maxUsers: number;
  modules: string[];
  startsAt: string | null;
  endsAt: string | null;
  createdAt: string;
};

type Payment = {
  id: number;
  tenantName: string;
  subscriptionId: number;
  planName: string;
  amount: string;
  currency: string;
  method: string;
  reference: string;
  paidAt: string;
  status: string;
  notes: string;
  recordedBy: string;
  reviewedBy: string | null;
  invoiceNumber: string | null;
};

type Invoice = {
  id: number;
  tenantName: string;
  invoiceNumber: string;
  amount: string;
  currency: string;
  issueDate: string;
  dueDate: string | null;
  status: "draft" | "open" | "paid" | "void" | "overdue";
  description: string;
};

type PlansResponse = { plans: Plan[]; modules: Module[] };
type SubscriptionsResponse = {
  subscriptions: Subscription[];
  tenants: Tenant[];
  plans: Plan[];
};
type PaymentsResponse = {
  payments: Payment[];
  invoices: Invoice[];
  subscriptions: Subscription[];
};
type TenantModulesResponse = { tenant: Tenant; modules: TenantModule[] };
type TenantModule = Module & {
  status: "inherit" | "enabled" | "disabled" | "suspended";
  note: string;
  enabled: boolean;
};

type PlanForm = {
  code: string;
  name: string;
  description: string;
  price: string;
  currency: string;
  billingPeriod: "monthly" | "quarterly" | "yearly";
  durationMonths: string;
  maxUsers: string;
  modules: string[];
};

const EMPTY_PLAN_FORM: PlanForm = {
  code: "",
  name: "",
  description: "",
  price: "",
  currency: "GNF",
  billingPeriod: "monthly",
  durationMonths: "1",
  maxUsers: "10",
  modules: [],
};

type ModuleForm = {
  code: string;
  name: string;
  description: string;
  dependencies: string[];
  sortOrder: string;
};

const EMPTY_MODULE_FORM: ModuleForm = {
  code: "",
  name: "",
  description: "",
  dependencies: [],
  sortOrder: "0",
};

function ErrorMessage({ error }: { error: unknown }) {
  if (!(error instanceof Error)) return null;
  return (
    <p className="text-destructive text-sm" role="alert">
      {error.message}
    </p>
  );
}

function SectionHeader({ section }: { section: "plans" | "payments" | "modules" | "domains" }) {
  const { t } = useLocale();
  return (
    <section className="from-primary/10 via-card to-card rounded-2xl border bg-gradient-to-br p-6 sm:p-8">
      <Badge variant="secondary" className="mb-3">
        {t("platform.navigation")}
      </Badge>
      <h1 className="font-display text-3xl font-bold tracking-tight">{t(`platform.${section}`)}</h1>
      <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-6">
        {t(`platform.section.description.${section}`)}
      </p>
    </section>
  );
}

function formatAmount(amount: string, currency: string, language: string) {
  return `${new Intl.NumberFormat(language, { maximumFractionDigits: 2 }).format(Number(amount))} ${currency}`;
}

function formatDate(value: string | null, language: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(new Date(value));
}

function PlanFormFields({
  value,
  modules,
  editing,
  onChange,
  t,
}: {
  value: PlanForm;
  modules: Module[];
  editing: boolean;
  onChange: (value: PlanForm) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.planName")}</span>
        <Input
          required
          maxLength={120}
          value={value.name}
          onChange={(event) => onChange({ ...value, name: event.target.value })}
        />
      </label>
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.planCode")}</span>
        <Input
          required
          maxLength={80}
          pattern="(?:[A-Za-z0-9_]|-)+"
          value={value.code}
          disabled={editing}
          onChange={(event) => onChange({ ...value, code: event.target.value })}
        />
      </label>
      <label className="space-y-1 text-sm sm:col-span-2">
        <span>{t("platform.billing.description")}</span>
        <Input
          maxLength={500}
          value={value.description}
          onChange={(event) => onChange({ ...value, description: event.target.value })}
        />
      </label>
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.price")}</span>
        <Input
          required
          type="number"
          min="0"
          step="0.01"
          value={value.price}
          onChange={(event) => onChange({ ...value, price: event.target.value })}
        />
      </label>
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.currency")}</span>
        <Input
          required
          minLength={3}
          maxLength={3}
          pattern="[A-Za-z]{3}"
          value={value.currency}
          onChange={(event) => onChange({ ...value, currency: event.target.value.toUpperCase() })}
        />
      </label>
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.billingPeriod")}</span>
        <select
          value={value.billingPeriod}
          onChange={(event) =>
            onChange({
              ...value,
              billingPeriod: event.target.value as PlanForm["billingPeriod"],
            })
          }
          className="border-input bg-background h-9 w-full rounded-md border px-3"
        >
          <option value="monthly">{t("platform.billing.monthly")}</option>
          <option value="quarterly">{t("platform.billing.quarterly")}</option>
          <option value="yearly">{t("platform.billing.yearly")}</option>
        </select>
      </label>
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.durationMonths")}</span>
        <Input
          required
          type="number"
          min="1"
          max="36"
          value={value.durationMonths}
          onChange={(event) => onChange({ ...value, durationMonths: event.target.value })}
        />
      </label>
      <label className="space-y-1 text-sm">
        <span>{t("platform.billing.maxUsers")}</span>
        <Input
          required
          type="number"
          min="1"
          value={value.maxUsers}
          onChange={(event) => onChange({ ...value, maxUsers: event.target.value })}
        />
      </label>
      <fieldset className="space-y-2 sm:col-span-2">
        <legend className="mb-2 text-sm font-medium">
          {t("platform.billing.includedModules")}
        </legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {modules.map((module) => (
            <label key={module.code} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.modules.includes(module.code)}
                onChange={(event) =>
                  onChange({
                    ...value,
                    modules: event.target.checked
                      ? [...value.modules, module.code]
                      : value.modules.filter((code) => code !== module.code),
                  })
                }
              />
              <span>{module.name}</span>
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

export function PlatformPlansPage() {
  const { language, t } = useLocale();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PlanForm>(EMPTY_PLAN_FORM);
  const [editingPlanId, setEditingPlanId] = useState<number | null>(null);
  const [tenantId, setTenantId] = useState("");
  const [planId, setPlanId] = useState("");
  const [planNotice, setPlanNotice] = useState("");
  const [subscriptionNotice, setSubscriptionNotice] = useState("");
  const plans = useQuery({
    queryKey: ["platform", "plans"],
    queryFn: () => api.get<PlansResponse>("platform/plans/"),
  });
  const subscriptions = useQuery({
    queryKey: ["platform", "subscriptions"],
    queryFn: () => api.get<SubscriptionsResponse>("platform/subscriptions/"),
  });
  const invalidateBilling = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "plans"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "subscriptions"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "payments"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
    ]);
  };
  const savePlan = useMutation({
    mutationFn: (payload: {
      code: string;
      name: string;
      description: string;
      price: string;
      currency: string;
      billing_period: PlanForm["billingPeriod"];
      duration_months: number;
      max_users: number;
      modules: string[];
    }) =>
      editingPlanId
        ? api.patch<Plan>(`platform/plans/${editingPlanId}/`, payload)
        : api.post<Plan>("platform/plans/", payload),
    onSuccess: async () => {
      setPlanNotice(t("platform.billing.planSaved"));
      setForm(EMPTY_PLAN_FORM);
      setEditingPlanId(null);
      await invalidateBilling();
    },
  });
  const assignSubscription = useMutation({
    mutationFn: () =>
      api.post<Subscription>("platform/subscriptions/", {
        tenant_id: Number(tenantId),
        plan_id: Number(planId),
      }),
    onSuccess: async () => {
      setSubscriptionNotice(t("platform.billing.subscriptionAssigned"));
      setTenantId("");
      setPlanId("");
      await invalidateBilling();
    },
  });
  const subscriptionAction = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "cancel" | "suspend" | "resume" }) =>
      api.post<Subscription>(`platform/subscriptions/${id}/${action}/`, {}),
    onSuccess: invalidateBilling,
  });

  function submitPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPlanNotice("");
    savePlan.mutate({
      code: form.code,
      name: form.name,
      description: form.description,
      price: form.price,
      currency: form.currency.toUpperCase(),
      billing_period: form.billingPeriod,
      duration_months: Number(form.durationMonths),
      max_users: Number(form.maxUsers),
      modules: form.modules,
    });
  }

  function editPlan(plan: Plan) {
    setForm({
      code: plan.code,
      name: plan.name,
      description: plan.description,
      price: plan.price,
      currency: plan.currency,
      billingPeriod: plan.billingPeriod as PlanForm["billingPeriod"],
      durationMonths: String(plan.durationMonths),
      maxUsers: String(plan.maxUsers),
      modules: plan.modules,
    });
    setEditingPlanId(plan.id);
    setPlanNotice("");
  }

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <SectionHeader section="plans" />
      {plans.isError || subscriptions.isError ? (
        <Card>
          <CardContent className="space-y-3 p-5">
            <p className="text-destructive text-sm" role="alert">
              {t("platform.section.loadError")}
            </p>
            <Button
              variant="outline"
              onClick={() => {
                void plans.refetch();
                void subscriptions.refetch();
              }}
            >
              {t("platform.section.retry")}
            </Button>
          </CardContent>
        </Card>
      ) : plans.isPending || subscriptions.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.plansTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <form className="space-y-4" onSubmit={submitPlan}>
                <PlanFormFields
                  value={form}
                  modules={plans.data.modules}
                  editing={editingPlanId !== null}
                  onChange={setForm}
                  t={t}
                />
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={savePlan.isPending}>
                    {editingPlanId
                      ? t("platform.billing.updatePlan")
                      : t("platform.billing.createPlan")}
                  </Button>
                  {editingPlanId && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setEditingPlanId(null);
                        setForm(EMPTY_PLAN_FORM);
                      }}
                    >
                      {t("platform.billing.cancelEdit")}
                    </Button>
                  )}
                </div>
                {planNotice && <p className="text-sm text-emerald-700">{planNotice}</p>}
                <ErrorMessage error={savePlan.error} />
              </form>
              <div className="grid gap-3 lg:grid-cols-2">
                {plans.data.plans.map((plan) => (
                  <article key={plan.id} className="rounded-xl border p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-semibold">{plan.name}</h3>
                        <p className="text-muted-foreground text-xs">{plan.code}</p>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => editPlan(plan)}
                      >
                        {t("platform.billing.edit")}
                      </Button>
                    </div>
                    <p className="mt-3 text-sm font-medium">
                      {formatAmount(plan.price, plan.currency, language)}
                    </p>
                    <p className="text-muted-foreground mt-1 text-sm">
                      {plan.durationMonths} {t("platform.billing.months")} · {plan.maxUsers}{" "}
                      {t("platform.billing.maxUsers").toLowerCase()}
                    </p>
                    <p className="text-muted-foreground mt-2 text-xs">
                      {plan.modules.length
                        ? plan.modules.join(", ")
                        : t("platform.billing.noModules")}
                    </p>
                  </article>
                ))}
                {plans.data.plans.length === 0 && (
                  <p className="text-muted-foreground text-sm">{t("platform.billing.noPlans")}</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.assignTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <form
                className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]"
                onSubmit={(event) => {
                  event.preventDefault();
                  setSubscriptionNotice("");
                  assignSubscription.mutate();
                }}
              >
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.tenant")}</span>
                  <select
                    required
                    value={tenantId}
                    onChange={(event) => setTenantId(event.target.value)}
                    className="border-input bg-background h-9 w-full rounded-md border px-3"
                  >
                    <option value="">{t("platform.billing.selectTenant")}</option>
                    {subscriptions.data.tenants.map((tenant) => (
                      <option key={tenant.id} value={tenant.id}>
                        {tenant.name} · {tenant.slug}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.plan")}</span>
                  <select
                    required
                    value={planId}
                    onChange={(event) => setPlanId(event.target.value)}
                    className="border-input bg-background h-9 w-full rounded-md border px-3"
                  >
                    <option value="">{t("platform.billing.selectPlan")}</option>
                    {subscriptions.data.plans.map((plan) => (
                      <option key={plan.id} value={plan.id}>
                        {plan.name} · {formatAmount(plan.price, plan.currency, language)}
                      </option>
                    ))}
                  </select>
                </label>
                <Button className="self-end" disabled={assignSubscription.isPending}>
                  {t("platform.billing.assign")}
                </Button>
              </form>
              <ErrorMessage error={assignSubscription.error} />
              {subscriptionNotice && (
                <p className="text-sm text-emerald-700">{subscriptionNotice}</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.subscriptionsTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {subscriptions.data.subscriptions.map((subscription) => (
                <article
                  key={subscription.id}
                  className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="font-medium">
                      {subscription.tenantName} · {subscription.planName}
                    </p>
                    <p className="text-muted-foreground text-sm">
                      {formatAmount(subscription.amount, subscription.currency, language)} ·{" "}
                      {t(`platform.billing.status.${subscription.status}`)} ·{" "}
                      {formatDate(subscription.endsAt, language)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {subscription.status === "active" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={subscriptionAction.isPending}
                        onClick={() =>
                          subscriptionAction.mutate({ id: subscription.id, action: "suspend" })
                        }
                      >
                        {t("platform.billing.suspend")}
                      </Button>
                    )}
                    {subscription.status === "suspended" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={subscriptionAction.isPending}
                        onClick={() =>
                          subscriptionAction.mutate({ id: subscription.id, action: "resume" })
                        }
                      >
                        {t("platform.billing.resume")}
                      </Button>
                    )}
                    {["pending", "active", "suspended"].includes(subscription.status) && (
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={subscriptionAction.isPending}
                        onClick={() =>
                          subscriptionAction.mutate({ id: subscription.id, action: "cancel" })
                        }
                      >
                        {t("platform.billing.cancelSubscription")}
                      </Button>
                    )}
                  </div>
                </article>
              ))}
              {subscriptions.data.subscriptions.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  {t("platform.billing.noSubscriptions")}
                </p>
              )}
              <ErrorMessage error={subscriptionAction.error} />
            </CardContent>
          </Card>
        </>
      )}
    </main>
  );
}

export function PlatformPaymentsPage() {
  const { language, t } = useLocale();
  const queryClient = useQueryClient();
  const [paymentStatus, setPaymentStatus] = useState("");
  const [subscriptionId, setSubscriptionId] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("mobile_money");
  const [reference, setReference] = useState("");
  const [paidAt, setPaidAt] = useState(
    new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10),
  );
  const [notes, setNotes] = useState("");
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [notice, setNotice] = useState("");
  const payments = useQuery({
    queryKey: ["platform", "payments", paymentStatus],
    queryFn: () =>
      api.get<PaymentsResponse>("platform/payments/", {
        status: paymentStatus || undefined,
      }),
  });
  const savePayment = useMutation({
    mutationFn: () => {
      const payload = new FormData();
      payload.set("subscription_id", String(Number(subscriptionId)));
      payload.set("amount", amount);
      payload.set("method", method);
      payload.set("reference", reference);
      payload.set("paid_at", paidAt);
      payload.set("notes", notes);
      if (proofFile) payload.set("proof_file", proofFile);
      return api.post<Payment>("platform/payments/", payload);
    },
    onSuccess: async () => {
      setNotice(t("platform.billing.paymentRecorded"));
      setSubscriptionId("");
      setAmount("");
      setReference("");
      setNotes("");
      setProofFile(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "payments"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "subscriptions"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
      ]);
    },
  });
  const paymentAction = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "confirm" | "reject" }) =>
      api.post<Payment>(`platform/payments/${id}/${action}/`, {}),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "payments"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "subscriptions"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
      ]);
    },
  });

  const selectedSubscription = payments.data?.subscriptions.find(
    (subscription) => String(subscription.id) === subscriptionId,
  );

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <SectionHeader section="payments" />
      {payments.isError ? (
        <Card>
          <CardContent className="space-y-3 p-5">
            <p className="text-destructive text-sm" role="alert">
              {t("platform.section.loadError")}
            </p>
            <Button variant="outline" onClick={() => void payments.refetch()}>
              {t("platform.section.retry")}
            </Button>
          </CardContent>
        </Card>
      ) : payments.isPending ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.recordPayment")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <form
                className="grid gap-4 sm:grid-cols-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  setNotice("");
                  savePayment.mutate();
                }}
              >
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.subscription")}</span>
                  <select
                    required
                    value={subscriptionId}
                    onChange={(event) => {
                      const nextId = event.target.value;
                      setSubscriptionId(nextId);
                      const nextSubscription = payments.data.subscriptions.find(
                        (item) => String(item.id) === nextId,
                      );
                      setAmount(nextSubscription?.amount ?? "");
                    }}
                    className="border-input bg-background h-9 w-full rounded-md border px-3"
                  >
                    <option value="">{t("platform.billing.selectSubscription")}</option>
                    {payments.data.subscriptions.map((subscription) => (
                      <option key={subscription.id} value={subscription.id}>
                        {subscription.tenantName} · {subscription.planName} ·{" "}
                        {formatAmount(subscription.amount, subscription.currency, language)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.amount")}</span>
                  <Input
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                  />
                </label>
                {selectedSubscription && (
                  <p className="text-muted-foreground text-xs sm:col-span-2">
                    {t("platform.billing.expectedAmount")}:{" "}
                    {formatAmount(
                      selectedSubscription.amount,
                      selectedSubscription.currency,
                      language,
                    )}
                  </p>
                )}
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.paymentMethod")}</span>
                  <select
                    value={method}
                    onChange={(event) => setMethod(event.target.value)}
                    className="border-input bg-background h-9 w-full rounded-md border px-3"
                  >
                    {(["mobile_money", "bank_transfer", "cash", "other"] as const).map((value) => (
                      <option key={value} value={value}>
                        {t(`platform.billing.method.${value}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.paidAt")}</span>
                  <Input
                    required
                    type="date"
                    value={paidAt}
                    onChange={(event) => setPaidAt(event.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.reference")}</span>
                  <Input
                    maxLength={120}
                    value={reference}
                    onChange={(event) => setReference(event.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.notes")}</span>
                  <Input
                    maxLength={500}
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.domains.proofFile")}</span>
                  <Input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={(event) => setProofFile(event.target.files?.[0] ?? null)}
                  />
                </label>
                <div className="flex flex-wrap items-end gap-3 sm:col-span-2">
                  <Button
                    disabled={savePayment.isPending || payments.data.subscriptions.length === 0}
                  >
                    {t("platform.billing.savePayment")}
                  </Button>
                  {notice && <p className="text-sm text-emerald-700">{notice}</p>}
                </div>
                <ErrorMessage error={savePayment.error} />
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>{t("platform.billing.paymentsTitle")}</CardTitle>
              <label className="text-sm">
                <span className="sr-only">{t("platform.billing.filterStatus")}</span>
                <select
                  value={paymentStatus}
                  onChange={(event) => setPaymentStatus(event.target.value)}
                  className="border-input bg-background h-9 rounded-md border px-3"
                >
                  <option value="">{t("platform.billing.allStatuses")}</option>
                  {(["pending", "confirmed", "rejected"] as const).map((value) => (
                    <option key={value} value={value}>
                      {t(`platform.billing.paymentStatus.${value}`)}
                    </option>
                  ))}
                </select>
              </label>
            </CardHeader>
            <CardContent className="space-y-3">
              {payments.data.payments.map((payment) => (
                <article
                  key={payment.id}
                  className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="space-y-1">
                    <p className="font-medium">
                      {payment.tenantName} · {payment.planName}
                    </p>
                    <p className="text-muted-foreground text-sm">
                      {formatAmount(payment.amount, payment.currency, language)} ·{" "}
                      {t(`platform.billing.method.${payment.method}`)} · {payment.paidAt}
                      {payment.reference ? ` · ${payment.reference}` : ""}
                      {payment.invoiceNumber ? ` · ${payment.invoiceNumber}` : ""}
                    </p>
                    <Badge variant={payment.status === "confirmed" ? "default" : "secondary"}>
                      {t(`platform.billing.paymentStatus.${payment.status}`)}
                    </Badge>
                  </div>
                  {payment.status === "pending" && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={paymentAction.isPending}
                        onClick={() => paymentAction.mutate({ id: payment.id, action: "confirm" })}
                      >
                        {t("platform.billing.confirm")}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={paymentAction.isPending}
                        onClick={() => paymentAction.mutate({ id: payment.id, action: "reject" })}
                      >
                        {t("platform.billing.reject")}
                      </Button>
                    </div>
                  )}
                </article>
              ))}
              {payments.data.payments.length === 0 && (
                <p className="text-muted-foreground text-sm">{t("platform.billing.noPayments")}</p>
              )}
              <ErrorMessage error={paymentAction.error} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.invoicesTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {payments.data.invoices.map((invoice) => (
                <article
                  key={invoice.id}
                  className="flex flex-col gap-2 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="font-medium">
                      {invoice.invoiceNumber} · {invoice.tenantName}
                    </p>
                    <p className="text-muted-foreground text-sm">
                      {invoice.description} · {formatDate(invoice.issueDate, language)}
                      {invoice.dueDate ? ` · ${formatDate(invoice.dueDate, language)}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium">
                      {formatAmount(invoice.amount, invoice.currency, language)}
                    </span>
                    <Badge variant={invoice.status === "paid" ? "default" : "secondary"}>
                      {t(`platform.billing.invoiceStatus.${invoice.status}`)}
                    </Badge>
                  </div>
                </article>
              ))}
              {payments.data.invoices.length === 0 && (
                <p className="text-muted-foreground text-sm">{t("platform.billing.noInvoices")}</p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </main>
  );
}

export function PlatformModulesPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [tenantId, setTenantId] = useState("");
  const [form, setForm] = useState<ModuleForm>(EMPTY_MODULE_FORM);
  const [notice, setNotice] = useState("");
  const modules = useQuery({
    queryKey: ["platform", "modules"],
    queryFn: () => api.get<Module[]>("platform/modules/"),
  });
  const tenants = useQuery({
    queryKey: ["platform", "subscriptions"],
    queryFn: () => api.get<SubscriptionsResponse>("platform/subscriptions/"),
  });
  const tenantModules = useQuery({
    queryKey: ["platform", "tenant-modules", tenantId],
    queryFn: () => api.get<TenantModulesResponse>(`platform/tenants/${tenantId}/modules/`),
    enabled: Boolean(tenantId),
  });
  const refreshModules = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "modules"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant-modules"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "plans"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
    ]);
  };
  const createModule = useMutation({
    mutationFn: () =>
      api.post<Module>("platform/modules/", {
        code: form.code,
        name: form.name,
        description: form.description,
        dependencies: form.dependencies,
        sort_order: Number(form.sortOrder),
      }),
    onSuccess: async () => {
      setForm(EMPTY_MODULE_FORM);
      setNotice(t("platform.billing.moduleCreated"));
      await refreshModules();
    },
  });
  const updateModule = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      api.patch<Module>(`platform/modules/${id}/`, { is_active: isActive }),
    onSuccess: refreshModules,
  });
  const updateTenantModule = useMutation({
    mutationFn: ({ moduleCode, status }: { moduleCode: string; status: TenantModule["status"] }) =>
      api.patch<TenantModulesResponse>(`platform/tenants/${tenantId}/modules/`, {
        module_code: moduleCode,
        status,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "tenant-modules", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
      ]);
    },
  });

  function submitModule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    createModule.mutate();
  }

  const loadError = modules.isError || tenants.isError;
  const loading = modules.isPending || tenants.isPending;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <SectionHeader section="modules" />
      {loadError ? (
        <Card>
          <CardContent className="space-y-3 p-5">
            <p className="text-destructive text-sm" role="alert">
              {t("platform.section.loadError")}
            </p>
            <Button
              variant="outline"
              onClick={() => {
                void modules.refetch();
                void tenants.refetch();
              }}
            >
              {t("platform.section.retry")}
            </Button>
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="bg-muted h-40 animate-pulse rounded-xl" />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.catalogTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <form className="grid gap-4 sm:grid-cols-2" onSubmit={submitModule}>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.moduleCode")}</span>
                  <Input
                    required
                    maxLength={50}
                    pattern="(?:[A-Za-z0-9_]|-)+"
                    value={form.code}
                    onChange={(event) => setForm({ ...form, code: event.target.value })}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.moduleName")}</span>
                  <Input
                    required
                    maxLength={100}
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                  />
                </label>
                <label className="space-y-1 text-sm sm:col-span-2">
                  <span>{t("platform.billing.description")}</span>
                  <Input
                    maxLength={300}
                    value={form.description}
                    onChange={(event) => setForm({ ...form, description: event.target.value })}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span>{t("platform.billing.sortOrder")}</span>
                  <Input
                    type="number"
                    min="0"
                    value={form.sortOrder}
                    onChange={(event) => setForm({ ...form, sortOrder: event.target.value })}
                  />
                </label>
                <fieldset className="space-y-2 sm:col-span-2">
                  <legend className="mb-2 text-sm font-medium">
                    {t("platform.billing.dependencies")}
                  </legend>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {modules.data.map((module) => (
                      <label key={module.code} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={form.dependencies.includes(module.code)}
                          onChange={(event) =>
                            setForm({
                              ...form,
                              dependencies: event.target.checked
                                ? [...form.dependencies, module.code]
                                : form.dependencies.filter((code) => code !== module.code),
                            })
                          }
                        />
                        <span>{module.name}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
                  <Button disabled={createModule.isPending}>
                    {t("platform.billing.addModule")}
                  </Button>
                  {notice && <span className="text-sm text-emerald-700">{notice}</span>}
                </div>
                <ErrorMessage error={createModule.error} />
              </form>
              <div className="divide-y rounded-xl border">
                {modules.data.map((module) => (
                  <article
                    key={module.id}
                    className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium">{module.name}</h3>
                        <Badge variant={module.isActive ? "default" : "secondary"}>
                          {module.isActive
                            ? t("platform.billing.active")
                            : t("platform.billing.inactive")}
                        </Badge>
                      </div>
                      <p className="text-muted-foreground text-xs">
                        {module.code}
                        {module.dependencies.length
                          ? ` · ${t("platform.billing.dependencies")}: ${module.dependencies.join(", ")}`
                          : ""}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={updateModule.isPending}
                      onClick={() =>
                        updateModule.mutate({ id: module.id, isActive: !module.isActive })
                      }
                    >
                      {module.isActive
                        ? t("platform.billing.deactivate")
                        : t("platform.billing.activate")}
                    </Button>
                  </article>
                ))}
                {modules.data.length === 0 && (
                  <p className="text-muted-foreground p-4 text-sm">
                    {t("platform.billing.noModules")}
                  </p>
                )}
              </div>
              <ErrorMessage error={updateModule.error} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("platform.billing.tenantModulesTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="block max-w-xl space-y-1 text-sm">
                <span>{t("platform.billing.selectTenant")}</span>
                <select
                  value={tenantId}
                  onChange={(event) => setTenantId(event.target.value)}
                  className="border-input bg-background h-9 w-full rounded-md border px-3"
                >
                  <option value="">{t("platform.billing.selectTenant")}</option>
                  {tenants.data.tenants.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>
                      {tenant.name} · {tenant.slug}
                    </option>
                  ))}
                </select>
              </label>
              {!tenantId ? (
                <p className="text-muted-foreground text-sm">
                  {t("platform.billing.chooseTenantModules")}
                </p>
              ) : tenantModules.isPending ? (
                <div className="bg-muted h-24 animate-pulse rounded-lg" />
              ) : tenantModules.isError ? (
                <div className="space-y-3">
                  <p className="text-destructive text-sm" role="alert">
                    {t("platform.section.loadError")}
                  </p>
                  <Button variant="outline" onClick={() => void tenantModules.refetch()}>
                    {t("platform.section.retry")}
                  </Button>
                </div>
              ) : (
                <div className="divide-y rounded-xl border">
                  {tenantModules.data.modules.map((module) => (
                    <article
                      key={module.code}
                      className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="font-medium">{module.name}</p>
                        <p className="text-muted-foreground text-sm">
                          {t("platform.billing.effectiveAccess")}:{" "}
                          {module.enabled
                            ? t("platform.billing.enabled")
                            : t("platform.billing.disabled")}
                        </p>
                      </div>
                      <label className="text-sm">
                        <span className="sr-only">{module.name}</span>
                        <select
                          value={module.status}
                          disabled={updateTenantModule.isPending}
                          onChange={(event) =>
                            updateTenantModule.mutate({
                              moduleCode: module.code,
                              status: event.target.value as TenantModule["status"],
                            })
                          }
                          className="border-input bg-background h-9 rounded-md border px-3"
                        >
                          {(["inherit", "enabled", "disabled", "suspended"] as const).map(
                            (value) => (
                              <option key={value} value={value}>
                                {t(`platform.billing.override.${value}`)}
                              </option>
                            ),
                          )}
                        </select>
                      </label>
                    </article>
                  ))}
                  {tenantModules.data.modules.length === 0 && (
                    <p className="text-muted-foreground p-4 text-sm">
                      {t("platform.billing.noModules")}
                    </p>
                  )}
                </div>
              )}
              <ErrorMessage error={updateTenantModule.error} />
            </CardContent>
          </Card>
        </>
      )}
    </main>
  );
}

type TenantDomain = {
  id: number;
  hostname: string;
  domainType: "application" | "storefront";
  verificationStatus: "pending" | "verified" | "rejected";
  isPrimary: boolean;
  verifiedAt: string | null;
};

type DomainChallenge = {
  recordName: string;
  recordType: "TXT";
  recordValue: string;
  expiresAt: string;
};

type TenantDomainsResponse = {
  tenant: Tenant;
  domains: TenantDomain[];
};

export function PlatformDomainsPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [tenantId, setTenantId] = useState("");
  const [hostname, setHostname] = useState("");
  const [domainType, setDomainType] = useState<TenantDomain["domainType"]>("application");
  const [reason, setReason] = useState("");
  const [challenge, setChallenge] = useState<DomainChallenge | null>(null);
  const tenants = useQuery({
    queryKey: ["platform", "subscriptions"],
    queryFn: () => api.get<SubscriptionsResponse>("platform/subscriptions/"),
  });
  const domains = useQuery({
    queryKey: ["platform", "tenant-domains", tenantId],
    queryFn: () => api.get<TenantDomainsResponse>(`platform/tenants/${tenantId}/domains/`),
    enabled: Boolean(tenantId),
  });
  const refreshDomains = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "tenant-domains", tenantId] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "audit"] }),
    ]);
  };
  const createDomain = useMutation({
    mutationFn: () =>
      api.post<{ domain: TenantDomain; challenge: DomainChallenge }>(
        `platform/tenants/${tenantId}/domains/`,
        { hostname, domain_type: domainType, reason },
      ),
    onSuccess: async (result) => {
      setHostname("");
      setChallenge(result.challenge);
      await refreshDomains();
    },
  });
  const domainAction = useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: number;
      action: "verify" | "renew-challenge" | "set-primary" | "remove";
    }) =>
      api.post<{ domain: TenantDomain; challenge?: DomainChallenge }>(
        `platform/domains/${id}/${action}/`,
        { reason },
      ),
    onSuccess: async (result) => {
      if (result.challenge) setChallenge(result.challenge);
      await refreshDomains();
    },
  });

  function submitDomain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setChallenge(null);
    createDomain.mutate();
  }

  const loading = tenants.isPending || (Boolean(tenantId) && domains.isPending);
  const loadError = tenants.isError || domains.isError;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6">
      <SectionHeader section="domains" />
      {loadError ? (
        <Card>
          <CardContent className="space-y-3 p-6">
            <p className="text-destructive text-sm" role="alert">
              {t("platform.section.loadError")}
            </p>
            <Button
              variant="outline"
              onClick={() => {
                if (tenants.isError) void tenants.refetch();
                if (domains.isError) void domains.refetch();
              }}
            >
              {t("platform.section.retry")}
            </Button>
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="bg-muted h-32 animate-pulse rounded-2xl" />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("platform.domains.manageTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <label className="block max-w-xl space-y-1 text-sm">
                <span>{t("platform.billing.selectTenant")}</span>
                <select
                  required
                  value={tenantId}
                  onChange={(event) => {
                    setTenantId(event.target.value);
                    setChallenge(null);
                  }}
                  className="border-input bg-background h-9 w-full rounded-md border px-3"
                >
                  <option value="">{t("platform.billing.selectTenant")}</option>
                  {tenants.data?.tenants.map((tenant) => (
                    <option key={tenant.id} value={tenant.id}>
                      {tenant.name} · {tenant.slug}
                    </option>
                  ))}
                </select>
              </label>
              <form onSubmit={submitDomain} className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
                <Input
                  required
                  maxLength={253}
                  placeholder="erp.example.com"
                  value={hostname}
                  onChange={(event) => setHostname(event.target.value)}
                  disabled={!tenantId}
                />
                <select
                  value={domainType}
                  onChange={(event) =>
                    setDomainType(event.target.value as TenantDomain["domainType"])
                  }
                  className="border-input bg-background h-9 rounded-md border px-3"
                  disabled={!tenantId}
                >
                  <option value="application">{t("platform.domains.application")}</option>
                  <option value="storefront">{t("platform.domains.storefront")}</option>
                </select>
                <Button
                  type="submit"
                  disabled={!tenantId || !reason.trim() || createDomain.isPending}
                >
                  {t("platform.domains.add")}
                </Button>
              </form>
              <label className="block max-w-xl space-y-1 text-sm">
                <span>{t("platform.domains.reason")}</span>
                <Input
                  required
                  maxLength={500}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </label>
              <ErrorMessage error={createDomain.error} />
              <ErrorMessage error={domainAction.error} />
              {challenge && (
                <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">
                  <p className="font-medium">{t("platform.domains.challengeInstructions")}</p>
                  <p className="mt-2 break-all">
                    <strong>{t("platform.domains.recordName")}:</strong> {challenge.recordName}
                  </p>
                  <p className="break-all">
                    <strong>{t("platform.domains.recordType")}:</strong> {challenge.recordType}
                  </p>
                  <p className="break-all">
                    <strong>{t("platform.domains.recordValue")}:</strong> {challenge.recordValue}
                  </p>
                  <p className="text-muted-foreground mt-2">
                    {t("platform.domains.challengeExpires")}:{" "}
                    {new Date(challenge.expiresAt).toLocaleString()}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
          {tenantId && domains.data && (
            <Card>
              <CardHeader>
                <CardTitle>{t("platform.domains.registeredTitle")}</CardTitle>
              </CardHeader>
              <CardContent className="divide-y">
                {domains.data.domains.map((domain) => (
                  <article
                    key={domain.id}
                    className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="break-all font-medium">{domain.hostname}</p>
                      <p className="text-muted-foreground text-sm">
                        {t(`platform.domains.${domain.domainType}`)} ·{" "}
                        {t(`platform.domains.status.${domain.verificationStatus}`)}
                        {domain.isPrimary ? ` · ${t("platform.domains.primary")}` : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {domain.verificationStatus !== "verified" ? (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={!reason.trim() || domainAction.isPending}
                            onClick={() => domainAction.mutate({ id: domain.id, action: "verify" })}
                          >
                            {t("platform.domains.verify")}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={!reason.trim() || domainAction.isPending}
                            onClick={() =>
                              domainAction.mutate({ id: domain.id, action: "renew-challenge" })
                            }
                          >
                            {t("platform.domains.renewChallenge")}
                          </Button>
                        </>
                      ) : !domain.isPrimary ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!reason.trim() || domainAction.isPending}
                          onClick={() =>
                            domainAction.mutate({ id: domain.id, action: "set-primary" })
                          }
                        >
                          {t("platform.domains.makePrimary")}
                        </Button>
                      ) : null}
                      {!domain.isPrimary && (
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={!reason.trim() || domainAction.isPending}
                          onClick={() => domainAction.mutate({ id: domain.id, action: "remove" })}
                        >
                          {t("platform.domains.remove")}
                        </Button>
                      )}
                    </div>
                  </article>
                ))}
                {domains.data.domains.length === 0 && (
                  <p className="text-muted-foreground py-4 text-sm">
                    {t("platform.domains.empty")}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </main>
  );
}
