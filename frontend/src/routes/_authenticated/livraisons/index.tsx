import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/livraisons/list/page";

export const Route = createFileRoute("/_authenticated/livraisons/")({
  ...PageRoute.options,
});
