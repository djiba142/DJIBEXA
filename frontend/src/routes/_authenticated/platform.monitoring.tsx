import { createFileRoute } from "@tanstack/react-router";

import { MonitoringRoute } from "@/pages/platform/monitoring/page";

export const Route = createFileRoute("/_authenticated/platform/monitoring")({
  ...MonitoringRoute.options,
});
