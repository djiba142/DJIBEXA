import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/storefront-settings/page";

export const Route = createFileRoute("/_authenticated/vitrine")({
  ...PageRoute.options,
});
