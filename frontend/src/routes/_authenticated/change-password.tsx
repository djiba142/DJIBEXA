import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/change-password/page";

export const Route = createFileRoute("/_authenticated/change-password")({
  ...PageRoute.options,
});
