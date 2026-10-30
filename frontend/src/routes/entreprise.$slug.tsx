import { createFileRoute } from "@tanstack/react-router";

import { PublicStorefrontPage } from "@/pages/company-storefront/public";

export const Route = createFileRoute("/entreprise/$slug")({
  ssr: false,
  component: StorefrontRoute,
});

function StorefrontRoute() {
  const { slug } = Route.useParams();
  return <PublicStorefrontPage slug={slug} />;
}
