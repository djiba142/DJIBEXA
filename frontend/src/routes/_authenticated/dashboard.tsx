import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/dashboard/page";

export const Route = createFileRoute("/_authenticated/dashboard")({
  ...PageRoute.options,
});
