import type { Product } from "./data"

export const SITE_URL = "https://aidermy.ru"

function serializeJsonLd(data: Record<string, unknown>): string {
  // Prevent a literal </script> inside user/content text from closing the tag.
  return JSON.stringify(data).replace(/</g, "\\u003c")
}

export function JsonLd({ data, id }: { data: Record<string, unknown>; id?: string }) {
  return (
    <script
      id={id}
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serializeJsonLd(data) }}
    />
  )
}

function absoluteImage(src: string | undefined | null): string | undefined {
  const value = (src || "").trim()
  if (!value || value.startsWith("data:") || value.startsWith("blob:")) return undefined
  if (value.startsWith("/")) return `${SITE_URL}${value}`
  if (value.startsWith("http://") || value.startsWith("https://")) return value
  return undefined
}

export function ProductJsonLd({ product }: { product: Product }) {
  const image = absoluteImage(product.image)
  const category = [product.category, product.subcategory].filter(Boolean).join(" / ")
  const inci = (product.ingredients || "").trim()
  const data: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description:
      `${product.brand ? `${product.brand} — ` : ""}${product.name}. ` +
      "Состав, персональная совместимость и рекомендации по уходу на айдерми.",
    brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined,
    category: category || undefined,
    sku: product.slug || String(product.id),
    mainEntityOfPage: SITE_URL,
    isPartOf: {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: "айдерми",
    },
  }
  if (image) data.image = [image]
  if (product.barcode && /^\d{8}$|^\d{12,14}$/.test(product.barcode)) {
    data.gtin = product.barcode
  }
  if (inci) {
    data.additionalProperty = [
      {
        "@type": "PropertyValue",
        name: "INCI",
        value: inci,
      },
    ]
  }
  // Remove undefined values so the emitted JSON stays clean for validators.
  Object.keys(data).forEach((key) => data[key] === undefined && delete data[key])
  return <JsonLd id="aidermy-product-jsonld" data={data} />
}

export function WebPageJsonLd({
  slug,
  title,
  description,
}: {
  slug: string
  title: string
  description: string
}) {
  const pageUrl = `${SITE_URL}/${encodeURIComponent(slug)}`
  return (
    <JsonLd
      id="aidermy-page-jsonld"
      data={{
        "@context": "https://schema.org",
        "@type": ["WebPage", "DigitalDocument"],
        "@id": `${pageUrl}#webpage`,
        url: pageUrl,
        name: title,
        description,
        inLanguage: "ru-RU",
        isPartOf: {
          "@type": "WebSite",
          "@id": `${SITE_URL}/#website`,
          url: SITE_URL,
          name: "айдерми",
        },
        publisher: {
          "@type": "Organization",
          "@id": `${SITE_URL}/#organization`,
          name: "айдерми",
          url: SITE_URL,
        },
      }}
    />
  )
}
