import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/mise-en-service/page";

export const Route = createFileRoute("/_authenticated/mise-en-service")({
  ...PageRoute.options,
});
