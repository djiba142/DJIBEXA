import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Settings2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { RequirePermission } from "@/components/RequirePermission";
import { useAuth } from "@/lib/auth";
import { formatNumber } from "@/lib/format";
import { useLocale } from "@/lib/locale";
import type { AppRole, StoredRole } from "@/lib/permissions";

export const PageRoute = createFileRoute("/_authenticated/utilisateurs")({
  head: () => ({
    meta: [
      { title: "Utilisateurs — ERP DJIBEXA" },
      {
        name: "description",
        content:
          "Gestion des comptes du personnel : création des accès vendeurs et propriétaires de DJIBEXA.",
      },
      { property: "og:title", content: "Utilisateurs — DJIBEXA" },
      { property: "og:description", content: "Comptes du personnel de l'ERP." },
    ],
  }),
  component: UtilisateursPage,
});
function UtilisateursPage() {
  return (
    <RequirePermission permission="users.manage">
      <Utilisateurs />
    </RequirePermission>
  );
}

function Utilisateurs() {
  const { t } = useLocale();
  const roleLabels: Record<AppRole, string> = {
    admin: t("role.admin"),
    stock: t("role.stock"),
    sales: t("role.sales"),
  };
  const { hasRole, session, refreshSession } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    phone: "",
    email: "",
    roles: ["sales"] as AppRole[],
  });
  const [editingUser, setEditingUser] = useState<{ id: number; roles: AppRole[] } | null>(null);

  const { data: users } = useQuery({
    queryKey: ["staff"],
    queryFn: () =>
      api.list<{
        id: number;
        username: string;
        first_name: string;
        last_name: string;
        phone: string;
        role: StoredRole;
        roles?: AppRole[];
        is_active: boolean;
      }>("users/"),
  });

  const createMut = useMutation({
    mutationFn: async () => {
      const username = (form.email.split("@")[0] ?? "").toLowerCase().replace(/[^a-z0-9._-]/g, "");
      await api.post("users/", {
        ...form,
        role: form.roles[0],
        username,
        email: form.email.toLowerCase(),
      });
    },
    onSuccess: () => {
      toast.success(t("users.created"));
      setOpen(false);
      setForm({
        first_name: "",
        last_name: "",
        phone: "",
        email: "",
        roles: ["sales"],
      });
      void qc.invalidateQueries({ queryKey: ["staff"] });
    },
    onError: (e: Error) => toast.error(t("users.createError"), { description: e.message }),
  });

  const rolesMut = useMutation({
    mutationFn: async () => {
      if (!editingUser || editingUser.roles.length === 0) {
        throw new Error(t("users.rolesRequired"));
      }
      await api.patch(`users/${editingUser.id}/`, { roles: editingUser.roles });
    },
    onSuccess: async () => {
      toast.success(t("users.rolesUpdated"));
      if (editingUser?.id === session?.user.id) await refreshSession();
      setEditingUser(null);
      void qc.invalidateQueries({ queryKey: ["staff"] });
    },
    onError: (e: Error) => toast.error(t("users.rolesError"), { description: e.message }),
  });

  const deleteMut = useMutation({
    mutationFn: async (userId: number) => api.patch(`users/${userId}/`, { is_active: false }),
    onSuccess: () => {
      toast.success(t("users.deactivated"));
      void qc.invalidateQueries({ queryKey: ["staff"] });
    },
    onError: (e: Error) => toast.error(t("users.deactivateError"), { description: e.message }),
  });

  if (!hasRole("admin")) {
    return (
      <div className="panel p-10 text-center">
        <p className="text-muted-foreground text-sm">{t("users.ownerOnly")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold uppercase">{t("users.title")}</h1>
          <p className="text-muted-foreground text-sm">
            {t("users.accountCount", { count: formatNumber(users?.length ?? 0) })}
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>{t("users.new")}</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("users.createAccess")}</DialogTitle>
            </DialogHeader>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                createMut.mutate();
              }}
            >
              <div className="space-y-1.5">
                <Label>{t("users.name")}</Label>
                <Input
                  required
                  value={`${form.first_name} ${form.last_name}`.trim()}
                  onChange={(e) => {
                    const [first_name = "", ...last] = e.target.value.split(" ");
                    setForm({ ...form, first_name, last_name: last.join(" ") });
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.phone")}</Label>
                <Input
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label>{t("users.email")}</Label>
                <Input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </div>
              <p className="text-muted-foreground text-xs">{t("users.temporaryPassword")}</p>
              <div className="space-y-2">
                <Label>{t("users.roles")}</Label>
                {(["admin", "stock", "sales"] as const).map((availableRole) => (
                  <label
                    key={availableRole}
                    className="flex min-h-11 items-center gap-3 rounded-md border px-3"
                  >
                    <input
                      type="checkbox"
                      checked={form.roles.includes(availableRole)}
                      onChange={(event) => {
                        const roles = event.target.checked
                          ? [...form.roles, availableRole]
                          : form.roles.filter((assignedRole) => assignedRole !== availableRole);
                        setForm({ ...form, roles });
                      }}
                    />
                    <span>{roleLabels[availableRole]}</span>
                  </label>
                ))}
              </div>
              <Button
                type="submit"
                className="w-full"
                disabled={createMut.isPending || form.roles.length === 0}
              >
                {t("users.create")}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="panel overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("customers.name")}</TableHead>
              <TableHead className="hidden sm:table-cell">{t("users.phone")}</TableHead>
              <TableHead>{t("users.role")}</TableHead>
              <TableHead>{t("users.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(users ?? []).map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">
                  {`${u.first_name} ${u.last_name}`.trim() || u.username}
                </TableCell>
                <TableCell className="hidden sm:table-cell">{u.phone ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant={u.is_active ? "default" : "secondary"}>
                    {u.role === "viewer"
                      ? t("users.legacyViewer")
                      : (u.roles ?? [u.role])
                          .map((assignedRole) => roleLabels[assignedRole])
                          .join(" + ")}
                    {u.is_active ? "" : ` · ${t("users.deactivated")}`}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    {u.role !== "viewer" && (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={t("users.configureRoles")}
                        onClick={() =>
                          setEditingUser({
                            id: u.id,
                            roles: u.roles ?? (u.role === "viewer" ? [] : [u.role]),
                          })
                        }
                      >
                        <Settings2 className="size-4" />
                      </Button>
                    )}
                    {u.is_active && u.id !== session?.user.id && (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={t("users.deactivate")}
                        disabled={deleteMut.isPending}
                        onClick={() => deleteMut.mutate(u.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Dialog
        open={editingUser !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setEditingUser(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("users.configureRoles")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            {(["admin", "stock", "sales"] as const).map((availableRole) => (
              <label
                key={availableRole}
                className="flex min-h-11 items-center gap-3 rounded-md border px-3"
              >
                <input
                  type="checkbox"
                  checked={editingUser?.roles.includes(availableRole) ?? false}
                  onChange={(event) => {
                    setEditingUser((current) => {
                      if (!current) return current;
                      const roles = event.target.checked
                        ? [...current.roles, availableRole]
                        : current.roles.filter((assignedRole) => assignedRole !== availableRole);
                      return { ...current, roles };
                    });
                  }}
                />
                <span>{roleLabels[availableRole]}</span>
              </label>
            ))}
          </div>
          <Button
            onClick={() => rolesMut.mutate()}
            disabled={rolesMut.isPending || !editingUser?.roles.length}
          >
            {t("common.save")}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
