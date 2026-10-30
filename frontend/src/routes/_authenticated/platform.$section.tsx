import { createFileRoute } from "@tanstack/react-router";

import { PlatformSectionPage } from "@/pages/platform/section/page";

function PlatformSectionRoute() {
  const { section } = Route.useParams();
  return <PlatformSectionPage section={section} />;
}

export const Route = createFileRoute("/_authenticated/platform/$section")({
  component: PlatformSectionRoute,
});
