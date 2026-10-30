import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type StorefrontContent = {
  title: string;
  industry: string;
  tagline: string;
  description: string;
  phone: string;
  email: string;
  address: string;
  city: string;
  primary_color: string;
  accent_color: string;
  services: string[];
  categories: string[];
  sections: {
    about: boolean;
    services: boolean;
    categories: boolean;
    contact: boolean;
  };
};

type PublicStorefront = {
  tenant_slug: string;
  content: StorefrontContent | null;
  published_at: string | null;
  legacy_fallback?: boolean;
  assets?: {
    logo: string | null;
    cover: string | null;
  };
};

export type PublicStorefrontProduct = {
  name: string;
  brand: string;
  image: string;
};

export function usePublicStorefront(slug: string) {
  return useQuery({
    queryKey: ["public-storefront", slug],
    queryFn: () => api.get<PublicStorefront>(`core/public/storefront/${slug}/`),
    retry: false,
  });
}

export function usePublicStorefrontProducts(slug: string, enabled: boolean) {
  return useQuery({
    queryKey: ["public-storefront-products", slug],
    queryFn: () => api.get<PublicStorefrontProduct[]>(`core/public/storefront/${slug}/products/`),
    enabled,
    retry: false,
  });
}
