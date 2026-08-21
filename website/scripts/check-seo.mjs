import { readFile } from "node:fs/promises";

const origin = "https://soljan-alsharq.com";
const pages = new Map([
  ["index.html", `${origin}/`],
  ["downloads.html", `${origin}/downloads`],
  ["privacy.html", `${origin}/privacy`],
  ["terms.html", `${origin}/terms`],
  ["support.html", `${origin}/support`],
  ["accessibility.html", `${origin}/accessibility`]
]);

for (const [filename, canonical] of pages) {
  const html = await readFile(new URL(`../public/${filename}`, import.meta.url), "utf8");
  const canonicalMarkup = `<link rel="canonical" href="${canonical}">`;
  if (!html.includes(canonicalMarkup)) {
    throw new Error(`${filename} must declare ${canonical} as its canonical URL.`);
  }
  if (/href="[^"]+\.html(?:[?#][^"]*)?"/i.test(html)) {
    throw new Error(`${filename} contains an internal link that triggers an HTML redirect.`);
  }
}

const notFound = await readFile(new URL("../public/404.html", import.meta.url), "utf8");
if (!notFound.includes('<meta name="robots" content="noindex">')) {
  throw new Error("404.html must remain excluded from search indexing.");
}

const sitemap = await readFile(new URL("../public/sitemap.xml", import.meta.url), "utf8");
const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
const expectedUrls = [...pages.values()];
if (
  sitemapUrls.length !== expectedUrls.length ||
  expectedUrls.some((url) => !sitemapUrls.includes(url)) ||
  sitemapUrls.some((url) => url.includes("www.") || url.endsWith(".html"))
) {
  throw new Error("sitemap.xml must contain only the final canonical page URLs.");
}

console.log(`SEO canonical and sitemap checks passed for ${pages.size} pages.`);
