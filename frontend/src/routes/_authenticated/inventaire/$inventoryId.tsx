import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/inventaire/detail/page";

export const Route = createFileRoute("/_authenticated/inventaire/$inventoryId")({
  ...PageRoute.options,
});
