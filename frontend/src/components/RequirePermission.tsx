import { useNavigate } from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import type { Permission } from "@/lib/permissions";

/** Bloque l'affichage d'une page si le rôle courant n'a pas la permission requise. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { can, role } = useAuth();
  const { t } = useLocale();
  const navigate = useNavigate();
  const allowed = can(permission);

  useEffect(() => {
    if (role && !allowed) navigate({ to: "/dashboard", replace: true });
  }, [role, allowed, navigate]);

  if (!allowed) {
    return (
      <div className="panel mx-auto max-w-md p-6 text-center">
        <h2 className="text-lg font-semibold">{t("permission.denied")}</h2>
        <p className="text-muted-foreground mt-2 text-sm">{t("permission.message")}</p>
      </div>
    );
  }

  return <>{children}</>;
}
