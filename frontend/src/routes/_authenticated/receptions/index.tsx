import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/receptions/list/page";

export const Route = createFileRoute("/_authenticated/receptions/")({
  ...PageRoute.options,
});
