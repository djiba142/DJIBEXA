import { Link, useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  Bell,
  ChevronDown,
  LayoutDashboard,
  PackageCheck,
  ShoppingCart,
  WalletCards,
  ClipboardList,
  Handshake,
  FileText,
  Receipt,
  Package,
  Boxes,
  Truck,
  Users,
  UserCog,
  UserCircle,
  Warehouse,
  FileBarChart,
  Settings,
  LifeBuoy,
  ShieldCheck,
  Activity,
  Database,
  BellRing,
  HardDrive,
  Wrench,
  CircleDollarSign,
  ClipboardClock,
  Store,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import type { Permission } from "@/lib/permissions";

const items: {
  titleKey: string;
  url: string;
  icon: typeof LayoutDashboard;
  permission: Permission;
  visibleToSales?: boolean;
  key: string;
}[] = [
  {
    key: "dashboard",
    titleKey: "nav.dashboard",
    url: "/dashboard",
    icon: LayoutDashboard,
    permission: "dashboard.view",
  },
  {
    key: "newSale",
    titleKey: "nav.newSale",
    url: "/ventes/nouvelle",
    icon: ShoppingCart,
    permission: "sales.create",
  },
  { key: "sales", titleKey: "nav.sales", url: "/ventes", icon: Receipt, permission: "sales.view" },
  {
    key: "customerQuotes",
    titleKey: "nav.customerQuotes",
    url: "/devis-clients",
    icon: FileText,
    permission: "sales.create",
  },
  {
    key: "products",
    titleKey: "nav.products",
    url: "/produits",
    icon: Package,
    permission: "products.view",
  },
  { key: "stock", titleKey: "nav.stock", url: "/stock", icon: Boxes, permission: "stock.view" },
  {
    key: "cartonStock",
    titleKey: "nav.cartonStock",
    url: "/stock-cartons",
    icon: Package,
    permission: "stock.view",
  },
  {
    key: "sampleStock",
    titleKey: "nav.sampleStock",
    url: "/stock-echantillons",
    icon: PackageCheck,
    permission: "stock.manage",
  },
  {
    key: "inventory",
    titleKey: "nav.inventory",
    url: "/inventaire",
    icon: ClipboardList,
    permission: "inventory.view",
  },
  {
    key: "warehouses",
    titleKey: "nav.warehouses",
    url: "/entrepots",
    icon: Warehouse,
    permission: "warehouses.view",
  },
  {
    key: "orders",
    titleKey: "nav.orders",
    url: "/commandes",
    icon: Truck,
    permission: "purchases.view",
  },
  {
    key: "receipts",
    titleKey: "nav.receipts",
    url: "/receptions",
    icon: PackageCheck,
    permission: "receptions.view",
  },
  {
    key: "deliveries",
    titleKey: "nav.deliveries",
    url: "/livraisons",
    icon: FileText,
    permission: "deliveries.view",
  },
  {
    key: "notifications",
    titleKey: "nav.notifications",
    url: "/notifications",
    icon: Bell,
    permission: "notifications.view",
  },
  {
    key: "credits",
    titleKey: "nav.credits",
    url: "/credits",
    icon: WalletCards,
    permission: "credits.view",
  },
  {
    key: "customers",
    titleKey: "nav.customers",
    url: "/clients",
    icon: Users,
    permission: "customers.view",
  },
  {
    key: "partners",
    titleKey: "nav.partners",
    url: "/partenaires",
    icon: Handshake,
    permission: "partners.view",
  },
  {
    key: "reports",
    titleKey: "nav.reports",
    url: "/rapports",
    icon: BarChart3,
    permission: "sales.view",
  },
  {
    key: "inventoryReports",
    titleKey: "nav.inventoryReports",
    url: "/rapports-inventaire",
    icon: FileBarChart,
    permission: "inventory.view",
  },
  {
    key: "users",
    titleKey: "nav.users",
    url: "/utilisateurs",
    icon: UserCog,
    permission: "users.manage",
  },
  {
    key: "storefront",
    titleKey: "nav.storefront",
    url: "/vitrine",
    icon: Store,
    permission: "users.manage",
  },
  {
    key: "settings",
    titleKey: "nav.settings",
    url: "/parametres",
    icon: Settings,
    permission: "users.manage",
  },
  {
    key: "setupGuide",
    titleKey: "nav.setupGuide",
    url: "/mise-en-service",
    icon: ClipboardList,
    permission: "users.manage",
  },
  {
    key: "profile",
    titleKey: "nav.profile",
    url: "/profil",
    icon: UserCircle,
    permission: "profile.view",
  },
  { key: "help", titleKey: "nav.help", url: "/aide", icon: LifeBuoy, permission: "profile.view" },
];

const QUICK_ACCESS_ITEMS = ["dashboard", "newSale", "sales", "customerQuotes", "notifications"];
const COMMERCIAL_ITEMS = ["products", "customers", "partners", "credits"];
const STOCK_ITEMS = [
  "stock",
  "cartonStock",
  "inventory",
  "sampleStock",
  "warehouses",
  "orders",
  "receipts",
  "deliveries",
];
const REPORT_ADMIN_ITEMS = [
  "reports",
  "inventoryReports",
  "users",
  "storefront",
  "settings",
  "setupGuide",
];
const ACCOUNT_ITEMS = ["profile", "help"];

const PLATFORM_SECTIONS = [
  { section: "services", key: "platform.services", icon: Database },
  { section: "incidents", key: "platform.incidents", icon: BellRing },
  { section: "security", key: "platform.security", icon: ShieldCheck },
  { section: "backups", key: "platform.backups", icon: HardDrive },
  { section: "maintenance", key: "platform.maintenance", icon: Wrench },
  { section: "plans", key: "platform.plans", icon: PackageCheck },
  { section: "support", key: "platform.support", icon: LifeBuoy },
  { section: "resources", key: "platform.resources", icon: CircleDollarSign },
  { section: "audit", key: "platform.audit", icon: ClipboardClock },
] as const;

export function AppSidebar() {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  const { roles, can, isPlatformAdmin } = useAuth();
  const { t } = useLocale();
  const { isMobile, setOpenMobile } = useSidebar();
  const visibleItems = isPlatformAdmin
    ? []
    : items.filter(
        (item) => can(item.permission) || (item.visibleToSales && roles.includes("sales")),
      );
  const itemsByKey = new Map(visibleItems.map((item) => [item.key, item]));
  const itemsFor = (keys: string[]) =>
    keys.flatMap((key) => {
      const item = itemsByKey.get(key);
      return item ? [item] : [];
    });
  const quickAccessItems = itemsFor(QUICK_ACCESS_ITEMS);
  const commercialItems = itemsFor(COMMERCIAL_ITEMS);
  const stockItems = itemsFor(STOCK_ITEMS);
  const reportAdminItems = itemsFor(REPORT_ADMIN_ITEMS);
  const accountItems = itemsFor(ACCOUNT_ITEMS);
  const renderMenuItems = (menuItems: typeof visibleItems, matchNestedRoutes = false) =>
    menuItems.map((item) => (
      <SidebarMenuItem key={item.url}>
        <SidebarMenuButton
          asChild
          isActive={
            pathname === item.url || (matchNestedRoutes && pathname.startsWith(`${item.url}/`))
          }
          tooltip={t(item.titleKey)}
          onClick={() => {
            if (isMobile) setOpenMobile(false);
          }}
        >
          <Link to={item.url}>
            <item.icon />
            <span>{t(item.titleKey)}</span>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    ));
  const renderCollapsibleGroup = (
    groupItems: typeof visibleItems,
    titleKey: string,
    Icon: typeof LayoutDashboard,
    matchNestedRoutes = false,
  ) =>
    groupItems.length > 0 ? (
      <Collapsible
        key={titleKey}
        defaultOpen={groupItems.some(
          (item) => pathname === item.url || pathname.startsWith(`${item.url}/`),
        )}
      >
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <CollapsibleTrigger asChild>
                  <SidebarMenuButton>
                    <Icon />
                    <span>{t(titleKey)}</span>
                    <ChevronDown className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
              </SidebarMenuItem>
            </SidebarMenu>
            <CollapsibleContent>
              <SidebarMenu className="mt-1">
                {renderMenuItems(groupItems, matchNestedRoutes)}
              </SidebarMenu>
            </CollapsibleContent>
          </SidebarGroupContent>
        </SidebarGroup>
      </Collapsible>
    ) : null;

  return (
    <Sidebar collapsible="icon">
      <SidebarContent>
        {isPlatformAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel>{t("platform.navigation")}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={pathname === "/platform"}>
                    <Link to="/platform">
                      <ShieldCheck />
                      <span>{t("platform.overview")}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={pathname === "/platform/monitoring"}>
                    <Link to="/platform/monitoring">
                      <Activity />
                      <span>{t("platform.monitoring")}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                {PLATFORM_SECTIONS.map(({ section, key, icon: Icon }) => (
                  <SidebarMenuItem key={section}>
                    <SidebarMenuButton asChild isActive={pathname === `/platform/${section}`}>
                      <Link to="/platform/$section" params={{ section }}>
                        <Icon />
                        <span>{t(key)}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
        {quickAccessItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t("nav.mainActions")}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>{renderMenuItems(quickAccessItems)}</SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
        {renderCollapsibleGroup(commercialItems, "nav.commercial", Handshake)}
        {renderCollapsibleGroup(stockItems, "nav.stockManagement", Boxes, true)}
        {renderCollapsibleGroup(reportAdminItems, "nav.reportsAdministration", BarChart3, true)}
        {accountItems.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>{t("nav.account")}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>{renderMenuItems(accountItems)}</SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
    </Sidebar>
  );
}
