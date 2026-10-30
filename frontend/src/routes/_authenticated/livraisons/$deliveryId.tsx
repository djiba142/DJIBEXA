import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/livraisons/detail/page";

export const Route = createFileRoute("/_authenticated/livraisons/$deliveryId")({
  ...PageRoute.options,
});
