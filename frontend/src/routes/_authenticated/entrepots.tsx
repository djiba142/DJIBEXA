import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/entrepots/page";

export const Route = createFileRoute("/_authenticated/entrepots")({
  ...PageRoute.options,
});
