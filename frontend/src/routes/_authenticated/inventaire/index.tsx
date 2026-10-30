import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/inventaire/list/page";

export const Route = createFileRoute("/_authenticated/inventaire/")({
  ...PageRoute.options,
});
