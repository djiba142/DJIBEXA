import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/notifications/page";

export const Route = createFileRoute("/_authenticated/notifications")({
  ...PageRoute.options,
});
