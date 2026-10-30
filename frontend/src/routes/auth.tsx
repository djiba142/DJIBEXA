import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/auth/page";

export const Route = createFileRoute("/auth")({
  ...PageRoute.options,
});
