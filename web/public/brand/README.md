# Brand assets: provenance

Owner decision **D22** (ADR-0001, 2026-10-15): apply Almamlaka TV branding from the official website. Assets are
self-hosted and never hotlinked. The prototype disclaimer stays on every page.

| File | Source (fetched 2026-10-15) | Notes |
|---|---|---|
| `almamlaka-logo.png` | `https://almamlakatv.com//storage/media/8dd573ba-8c8c-4899-8fdf-0bccd9ee5b2e.png` (the site's `og:image`) | Red Arabic wordmark «المملكة», 159×47, transparent background |
| `almamlaka-logo.webp` | the same media ID as `.webp` (the site header logo, alt «قناة المملكة») | 159×47 |
| `almamlaka-favicon.png` | the site's `<link rel="icon">` (`/storage/media/045ebc98-…png`, served as PNG) | 48×48, white wordmark on red |

The colours are in `src/index.css`, taken from the site's own CSS custom properties.

**Typeface (owner decision D25):** the site's own `ALMAMLAKAFONT` is used for Arabic and English, as on the site.
`public/fonts/ALMAMLAKAFONT-{Light,Medium,Extrabold}.woff2` (not redistributed in the public repository) come unmodified from
`https://almamlakatv.com/fonts/` (fetched 2026-10-15). They cover Arabic, Latin, both digit styles and
punctuation. The licence is not published: use only in this Almamlaka prototype.

The logo files are small rasters. Replace them with vector originals when the owner supplies brand samples.
