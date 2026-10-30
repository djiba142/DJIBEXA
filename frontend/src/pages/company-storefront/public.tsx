import { Link } from "@tanstack/react-router";
import { ArrowLeft, ImageOff, Mail, MapPin, Phone } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  type PublicStorefrontProduct,
  usePublicStorefront,
  usePublicStorefrontProducts,
} from "@/pages/company-storefront/public-api";

function PublicProductCard({ product }: { product: PublicStorefrontProduct }) {
  const [imageUnavailable, setImageUnavailable] = useState(false);

  return (
    <article className="bg-background overflow-hidden rounded-2xl border shadow-sm">
      <div className="bg-muted aspect-[4/3] overflow-hidden">
        {imageUnavailable ? (
          <div className="text-muted-foreground flex size-full flex-col items-center justify-center gap-2 text-sm">
            <ImageOff className="size-7" aria-hidden="true" />
            <span>Photo indisponible</span>
          </div>
        ) : (
          <img
            src={product.image}
            alt={product.brand ? `${product.name} — ${product.brand}` : product.name}
            className="size-full object-cover transition-transform duration-300 hover:scale-105"
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setImageUnavailable(true)}
          />
        )}
      </div>
      <div className="p-4">
        {product.brand && (
          <p className="text-muted-foreground text-xs font-semibold uppercase tracking-wide">
            {product.brand}
          </p>
        )}
        <h3 className="mt-1 font-semibold">{product.name}</h3>
      </div>
    </article>
  );
}

export function PublicStorefrontPage({ slug, fallback }: { slug: string; fallback?: ReactNode }) {
  const { data, isLoading, error } = usePublicStorefront(slug);
  const productsQuery = usePublicStorefrontProducts(
    slug,
    Boolean(data?.content && !data.legacy_fallback),
  );

  useEffect(() => {
    if (!data?.content) return;
    document.title = `${data.content.title} — DJIBEXA`;
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) {
      description.content = data.content.tagline || data.content.description;
    }
  }, [data]);

  if (fallback && data?.legacy_fallback) {
    return fallback;
  }

  if (isLoading) {
    return (
      <main className="mx-auto min-h-screen max-w-5xl px-6 py-20">
        <p role="status">Chargement de la vitrine…</p>
      </main>
    );
  }

  if (error || !data || !data.content) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-start justify-center gap-5 px-6 py-20">
        <h1 className="font-display text-3xl font-bold">Vitrine indisponible</h1>
        <p className="text-muted-foreground">
          Cette vitrine n’est pas publiée ou l’entreprise n’est pas active.
        </p>
        <Button asChild variant="outline">
          <Link to="/">
            <ArrowLeft className="mr-2 size-4" aria-hidden="true" />
            Accueil DJIBEXA
          </Link>
        </Button>
      </main>
    );
  }

  const { content } = data;
  const assets = data.assets;
  return (
    <div
      className="bg-background min-h-screen"
      style={
        {
          "--storefront-primary": content.primary_color,
          "--storefront-accent": content.accent_color,
        } as CSSProperties
      }
    >
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4">
          <Link to="/" className="flex min-w-0 items-center gap-3">
            {assets?.logo && (
              <img src={assets.logo} alt="" className="h-10 max-w-28 object-contain" />
            )}
            <span
              className="font-display truncate text-xl font-bold"
              style={{ color: content.primary_color }}
            >
              {content.title}
            </span>
          </Link>
          <Button asChild size="sm">
            <Link to="/auth">Espace de gestion</Link>
          </Button>
        </div>
      </header>
      <main>
        <section
          className="px-5 py-20 text-white sm:py-28"
          style={{
            backgroundImage: assets?.cover
              ? `linear-gradient(135deg, ${content.primary_color}dd, ${content.accent_color}cc), url("${assets.cover}")`
              : `linear-gradient(135deg, ${content.primary_color}, ${content.accent_color})`,
            backgroundPosition: "center",
            backgroundSize: "cover",
          }}
        >
          <div className="mx-auto max-w-6xl space-y-5">
            {content.industry && (
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-white/75">
                {content.industry}
              </p>
            )}
            <h1 className="font-display max-w-4xl text-4xl font-bold leading-tight sm:text-6xl">
              {content.title}
            </h1>
            {content.tagline && <p className="max-w-3xl text-xl font-medium">{content.tagline}</p>}
          </div>
        </section>

        {content.sections.about && content.description && (
          <section className="mx-auto max-w-6xl px-5 py-14">
            <h2 className="font-display text-2xl font-bold">À propos</h2>
            <p className="text-muted-foreground mt-3 max-w-3xl leading-7">{content.description}</p>
          </section>
        )}

        {content.sections.services && content.services.length > 0 && (
          <section className="bg-muted/30 border-y px-5 py-14">
            <div className="mx-auto max-w-6xl">
              <h2 className="font-display text-2xl font-bold">Nos services</h2>
              <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {content.services.map((service) => (
                  <li key={service} className="bg-background rounded-xl border p-5 font-medium">
                    {service}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        {content.sections.categories && content.categories.length > 0 && (
          <section className="mx-auto max-w-6xl px-5 py-14">
            <h2 className="font-display text-2xl font-bold">Nos catégories</h2>
            <ul className="mt-6 flex flex-wrap gap-3">
              {content.categories.map((category) => (
                <li
                  key={category}
                  className="rounded-full border px-4 py-2 text-sm font-medium"
                  style={{ borderColor: content.accent_color, color: content.primary_color }}
                >
                  {category}
                </li>
              ))}
            </ul>
          </section>
        )}

        {content.sections.contact &&
          (content.phone || content.email || content.address || content.city) && (
            <section className="bg-muted/30 border-t px-5 py-14">
              <div className="mx-auto max-w-6xl">
                <h2 className="font-display text-2xl font-bold">Nous contacter</h2>
                <address className="text-muted-foreground mt-5 flex flex-col gap-4 not-italic">
                  {content.phone && (
                    <a className="flex items-center gap-3" href={`tel:${content.phone}`}>
                      <Phone className="size-4" aria-hidden="true" />
                      {content.phone}
                    </a>
                  )}
                  {content.email && (
                    <a className="flex items-center gap-3" href={`mailto:${content.email}`}>
                      <Mail className="size-4" aria-hidden="true" />
                      {content.email}
                    </a>
                  )}
                  {(content.address || content.city) && (
                    <p className="flex items-center gap-3">
                      <MapPin className="size-4" aria-hidden="true" />
                      {[content.address, content.city].filter(Boolean).join(", ")}
                    </p>
                  )}
                </address>
              </div>
            </section>
          )}

        {productsQuery.isError && (
          <section className="mx-auto max-w-6xl px-5 py-8">
            <p className="text-muted-foreground" role="status">
              Les produits à découvrir ne sont pas disponibles pour le moment.
            </p>
          </section>
        )}

        {productsQuery.data && productsQuery.data.length > 0 && (
          <section className="mx-auto max-w-6xl px-5 py-14">
            <div className="mb-7">
              <p
                className="text-sm font-semibold uppercase tracking-[0.16em]"
                style={{ color: content.accent_color }}
              >
                La sélection du magasin
              </p>
              <h2 className="font-display mt-2 text-2xl font-bold sm:text-3xl">
                Quelques produits à découvrir
              </h2>
              <p className="text-muted-foreground mt-2">
                Découvrez une sélection de produits de notre catalogue.
              </p>
            </div>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {productsQuery.data.map((product, index) => (
                <PublicProductCard key={`${product.name}-${index}`} product={product} />
              ))}
            </div>
          </section>
        )}
      </main>
      <footer className="border-t px-5 py-6 text-center text-sm text-muted-foreground">
        {content.title}
      </footer>
    </div>
  );
}
