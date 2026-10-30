import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/stock-cartons/page";

export const Route = createFileRoute("/_authenticated/stock-cartons")({
  ...PageRoute.options,
});
