import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/company-storefront/kourouma/page";

export const Route = createFileRoute("/entreprise/kourouma-auto-parts")({
  ...PageRoute.options,
});
