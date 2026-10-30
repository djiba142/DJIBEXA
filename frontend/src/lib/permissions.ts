export type AppRole = "admin" | "stock" | "sales";
export type StoredRole = AppRole | "viewer";

/** Toutes les permissions de l'ERP. */
export const PERMISSIONS = [
  "dashboard.view",
  "sales.create",
  "sales.view",
  "sales.manage",
  "products.view",
  "products.manage",
  "stock.view",
  "stock.manage",
  "inventory.view",
  "inventory.manage",
  "customers.view",
  "customers.manage",
  "credits.view",
  "credits.manage",
  "purchases.view",
  "purchases.manage",
  "receptions.view",
  "receptions.manage",
  "deliveries.view",
  "deliveries.manage",
  "warehouses.view",
  "warehouses.manage",
  "transfers.request",
  "transfers.manage",
  "notifications.view",
  "partners.view",
  "partners.manage",
  "users.manage",
  "reports.view",
  "profile.view",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

const SALES_PERMISSIONS: Permission[] = [
  "dashboard.view",
  "sales.create",
  "sales.view",
  "products.view",
  "customers.view",
  "customers.manage",
  "credits.view",
  "credits.manage",
  "notifications.view",
  "profile.view",
];

const STOCK_PERMISSIONS: Permission[] = [
  "dashboard.view",
  "products.view",
  "products.manage",
  "stock.view",
  "inventory.view",
  "inventory.manage",
  "purchases.view",
  "purchases.manage",
  "receptions.view",
  "receptions.manage",
  "warehouses.view",
  "warehouses.manage",
  "transfers.request",
  "transfers.manage",
  "notifications.view",
  "profile.view",
];

export const ROLE_PERMISSIONS: Record<AppRole, readonly Permission[]> = {
  admin: PERMISSIONS,
  sales: SALES_PERMISSIONS,
  stock: STOCK_PERMISSIONS,
};

export const ROLE_LABELS: Record<AppRole, string> = {
  admin: "Administrateur",
  sales: "Vendeur",
  stock: "Gestionnaire de stock",
};

export function can(roles: AppRole | readonly AppRole[] | null, permission: Permission): boolean {
  if (!roles) return false;
  const assignedRoles: readonly AppRole[] = typeof roles === "string" ? [roles] : roles;
  return assignedRoles.some((role) => ROLE_PERMISSIONS[role].includes(permission));
}
