import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/stock-manuel/page";

export const Route = createFileRoute("/_authenticated/stock-manuel")({
  ...PageRoute.options,
});
