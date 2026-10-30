import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import { can, type AppRole, type Permission } from "@/lib/permissions";
import { loadSettings, type AppSettings } from "@/lib/settings";

export type { AppRole } from "@/lib/permissions";

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: AppRole;
  roles?: AppRole[];
  is_platform_admin: boolean;
  phone: string;
  photo: string | null;
  is_active: boolean;
  must_change_password: boolean;
  preferred_language: "fr" | "en" | "ar" | "zh";
};

type AuthSession = { user: AuthUser };

type AuthMessageKey =
  "serverUnavailable" | "unknownError" | "signOutFailed" | "sessionExpired" | "idleExpired";

const AUTH_MESSAGES: Record<AppSettings["language"], Record<AuthMessageKey, string>> = {
  fr: {
    serverUnavailable: "Connexion au serveur impossible",
    unknownError: "Erreur inconnue.",
    signOutFailed: "Déconnexion impossible",
    sessionExpired: "Session expirée",
    idleExpired: "Vous avez été déconnecté après 30 minutes d'inactivité.",
  },
  en: {
    serverUnavailable: "Unable to connect to the server",
    unknownError: "Unknown error.",
    signOutFailed: "Unable to sign out",
    sessionExpired: "Session expired",
    idleExpired: "You were signed out after 30 minutes of inactivity.",
  },
  ar: {
    serverUnavailable: "تعذر الاتصال بالخادم",
    unknownError: "خطأ غير معروف.",
    signOutFailed: "تعذر تسجيل الخروج",
    sessionExpired: "انتهت الجلسة",
    idleExpired: "تم تسجيل خروجك بعد 30 دقيقة من عدم النشاط.",
  },
  zh: {
    serverUnavailable: "无法连接服务器",
    unknownError: "未知错误。",
    signOutFailed: "无法退出登录",
    sessionExpired: "会话已过期",
    idleExpired: "您已因 30 分钟无操作而退出登录。",
  },
};

function authMessage(key: AuthMessageKey) {
  return AUTH_MESSAGES[loadSettings().language][key];
}

/** Déconnexion automatique après 30 minutes sans activité. */
const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const ACTIVITY_EVENTS = ["mousedown", "keydown", "touchstart", "scroll", "visibilitychange"];

type AuthValue = {
  session: AuthSession | null;
  loading: boolean;
  role: AppRole | null;
  roles: AppRole[];
  fullName: string;
  isOwner: boolean;
  isPlatformAdmin: boolean;
  /** Expiration de la session courante (ms epoch), null si déconnecté. */
  expiresAt: number | null;
  can: (permission: Permission) => boolean;
  hasRole: (role: AppRole) => boolean;
  signIn: (identifier: string, password: string) => Promise<void>;
  refreshSession: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthValue>({
  session: null,
  loading: true,
  role: null,
  roles: [],
  fullName: "",
  isOwner: false,
  isPlatformAdmin: false,
  expiresAt: null,
  can: () => false,
  hasRole: () => false,
  signIn: async () => {},
  refreshSession: async () => {},
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const lastActivity = useRef(Date.now());
  const session = useMemo<AuthSession | null>(() => (user ? { user } : null), [user]);
  const role = user?.role ?? null;
  const isPlatformAdmin = user?.is_platform_admin ?? false;
  const roles = useMemo<AppRole[]>(
    () => (isPlatformAdmin ? [] : user?.roles?.length ? user.roles : role ? [role] : []),
    [isPlatformAdmin, user?.roles, role],
  );
  const fullName = user ? `${user.first_name} ${user.last_name}`.trim() || user.username : "";

  const refreshSession = useCallback(async () => {
    try {
      const currentUser = await api.get<AuthUser>("users/me/");
      setUser(currentUser);
    } catch (error) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) {
        queryClient.clear();
        setUser(null);
      } else {
        toast.error(authMessage("serverUnavailable"), {
          description: error instanceof Error ? error.message : authMessage("unknownError"),
        });
      }
    } finally {
      setLoading(false);
    }
  }, [queryClient]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const signIn = useCallback(
    async (identifier: string, password: string) => {
      const response = await api.post<{ success: boolean; message: string; user: AuthUser }>(
        "users/login/",
        { identifier, password },
      );
      queryClient.clear();
      setUser(response.user);
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await api.post("users/logout/");
      queryClient.clear();
      setUser(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        queryClient.clear();
        setUser(null);
        return;
      }
      toast.error(authMessage("signOutFailed"), {
        description: error instanceof Error ? error.message : authMessage("unknownError"),
      });
    }
  }, [queryClient]);

  // Renouvellement anticipé du jeton + expiration d'inactivité.
  useEffect(() => {
    if (!session) return;
    const markActivity = () => {
      lastActivity.current = Date.now();
    };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, markActivity, { passive: true }));

    const timer = window.setInterval(() => {
      if (Date.now() - lastActivity.current > IDLE_TIMEOUT_MS) {
        void signOut();
        toast.info(authMessage("sessionExpired"), {
          description: authMessage("idleExpired"),
        });
      }
    }, 60_000);

    return () => {
      window.clearInterval(timer);
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, markActivity));
    };
  }, [session, signOut]);

  const value = useMemo<AuthValue>(
    () => ({
      session,
      loading,
      role,
      roles,
      fullName,
      isOwner: roles.includes("admin"),
      isPlatformAdmin,
      expiresAt: null,
      can: (permission: Permission) => can(roles, permission),
      hasRole: (assignedRole: AppRole) => roles.includes(assignedRole),
      signIn,
      refreshSession,
      signOut,
    }),
    [session, loading, role, roles, fullName, isPlatformAdmin, signIn, refreshSession, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
