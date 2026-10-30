import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/sales/detail/page";

export const Route = createFileRoute("/_authenticated/ventes/$saleId")({
  ...PageRoute.options,
});
