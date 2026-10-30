import { createFileRoute } from "@tanstack/react-router";

import { PageRoute } from "@/pages/home/page";

export const Route = createFileRoute("/")({
  ...PageRoute.options,
});
