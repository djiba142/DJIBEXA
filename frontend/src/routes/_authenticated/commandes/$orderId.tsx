import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/commandes/detail/page";

export const Route = createFileRoute("/_authenticated/commandes/$orderId")({
  ...PageRoute.options,
});
