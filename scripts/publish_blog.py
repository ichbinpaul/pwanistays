#!/usr/bin/env python3
"""Render a reviewed blog draft for the branch-based GitHub Pages site."""
import base64
import binascii
from datetime import datetime
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from markdown_it import MarkdownIt

from site_chrome import SITE_FOOTER

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://pwanistays.com"
FOOTER_MARKER = "<!-- blog-footer-link -->"
SITEMAP_MARKER = "  <!-- property-sitemap.xml"
BLOG_LINK = '<li><a href="/blog/">Travel blog</a></li>'
FIELDS = {"title", "slug", "description", "image", "alt", "body"}
MARKDOWN = MarkdownIt("commonmark", {"html": False}).disable("image")


def safe_link(url):
    if any(character.isspace() or character == "\\" for character in url):
        return False
    parsed = urlsplit(url)
    if url.startswith("/") and not url.startswith("//"):
        return not parsed.netloc and not parsed.scheme
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username


MARKDOWN.validateLink = safe_link


def read_draft(code, root=ROOT):
    if not code or len(code) > 48000:
        raise ValueError("Enter a publish code from Blog Studio (maximum 48,000 characters).")
    try:
        draft = json.loads(base64.b64decode(code, validate=True).decode("utf-8"))
    except (binascii.Error, UnicodeError, ValueError) as error:
        raise ValueError("The publish code is invalid. Copy it again from Blog Studio.") from error
    if not isinstance(draft, dict) or set(draft) != FIELDS:
        raise ValueError("The draft has unexpected or missing fields.")
    if not all(isinstance(value, str) and value.strip() for value in draft.values()):
        raise ValueError("Complete every field in Blog Studio.")
    draft = {key: value.strip() for key, value in draft.items()}
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", draft["slug"]) or len(draft["slug"]) > 80:
        raise ValueError("Use a lowercase, hyphenated URL slug of up to 80 characters.")
    if len(draft["title"]) > 115 or len(draft["description"]) > 165 or len(draft["alt"]) > 180:
        raise ValueError("The title, search description or image description is too long.")
    if not re.fullmatch(r"/images/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:webp|jpe?g|png)", draft["image"]):
        raise ValueError("Use an existing WebP, JPEG or PNG image from /images/.")
    image = root / draft["image"].lstrip("/")
    if not image.is_file() or not image.resolve().is_relative_to(root / "images"):
        raise ValueError("The cover image is missing from the site.")
    if any(token.type == "heading_open" and token.tag not in ("h2", "h3")
           for token in MARKDOWN.parse(draft["body"])):
        raise ValueError("Use ## or ### for article headings. The title becomes the page heading.")
    if not re.search(r"[A-Za-z]{2}", draft["body"]):
        raise ValueError("Write the article before publishing.")
    return draft


def page(title, description, path, content, *, image, alt, schema, article=False):
    def attr(value):
        return escape(value, quote=True)

    safe_title, safe_description, safe_alt = map(attr, (title, description, alt))
    url = SITE + path
    image_url = SITE + image
    structured = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{safe_title} | PwaniStays</title>
  <meta name="description" content="{safe_description}">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <meta name="theme-color" content="#0d7a5f">
  <link rel="canonical" href="{url}">
  <link rel="icon" href="/favicon-32x32.png">
  <meta property="og:type" content="{'article' if article else 'website'}">
  <meta property="og:site_name" content="PwaniStays">
  <meta property="og:url" content="{url}">
  <meta property="og:title" content="{safe_title}">
  <meta property="og:description" content="{safe_description}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:alt" content="{safe_alt}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{safe_title}">
  <meta name="twitter:description" content="{safe_description}">
  <meta name="twitter:image" content="{image_url}">
  <meta name="twitter:image:alt" content="{safe_alt}">
  <link rel="stylesheet" href="/header.css">
  <link rel="stylesheet" href="/about.css?v=1">
  <link rel="stylesheet" href="/blog.css">
  <script src="/i18n.js" defer></script>
  <script src="/header-loader.js" defer></script>
  <script type="application/ld+json">{structured}</script>
</head>
<body class="about-page blog-page">
  <a class="about-skip" href="#main-content">Skip to content</a>
  <div id="site-header"></div>
  <main id="main-content" class="about-main about-wrap blog-main" tabindex="-1">
    {content}
  </main>
  {SITE_FOOTER}
</body>
</html>
"""


def blog_path(slug):
    return f"/blog/{slug}/"


def render_article(draft, published):
    path = blog_path(draft["slug"])
    title, description, image, alt = (draft[key] for key in ("title", "description", "image", "alt"))
    schema = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "mainEntityOfPage": SITE + path,
        "headline": title,
        "description": description,
        "image": SITE + image,
        "datePublished": published,
        "author": {"@type": "Organization", "name": "PwaniStays", "url": SITE + "/about"},
        "publisher": {"@type": "Organization", "name": "PwaniStays", "url": SITE},
    }
    date_label = datetime.fromisoformat(published).strftime("%d %B %Y").lstrip("0")
    content = f"""<nav class="blog-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> / <a href="/blog/">Travel blog</a> / <span aria-current="page">Article</span></nav>
    <article class="blog-article">
      <h1>{escape(title)}</h1>
      <p class="blog-byline">PwaniStays · <time datetime="{published}">{date_label}</time></p>
      <img class="blog-cover" src="{image}" alt="{escape(alt, quote=True)}" width="960" height="640" fetchpriority="high" decoding="async">
      <div class="blog-prose">{MARKDOWN.render(draft["body"])}</div>
    </article>"""
    return page(title, description, path, content, image=image, alt=alt, schema=schema, article=True)


def render_index(entries):
    latest = entries[0]
    cards = "\n".join(
        f'<article><h2><a href="{blog_path(item["slug"])}">{escape(item["title"])}</a></h2>'
        f'<p>{escape(item["description"])}</p></article>'
        for item in entries
    )
    content = f"""<nav class="blog-breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a> / <span aria-current="page">Travel blog</span></nav>
    <h1>Kenya coast travel blog</h1>
    <p class="blog-intro">Practical advice for choosing a stay and planning time on Kenya’s coast.</p>
    <div class="blog-grid">{cards}</div>"""
    return page("Kenya Coast Travel Blog", "Practical Kenya coast travel guides from PwaniStays.", "/blog/", content,
                image=latest["image"], alt=latest["alt"],
                schema={"@context": "https://schema.org", "@type": "Blog", "url": SITE + "/blog/",
                        "name": "Kenya Coast Travel Blog | PwaniStays"})


def publish(draft, root=ROOT):
    slug = draft["slug"]
    blog = root / "blog"
    article = blog / slug / "index.html"
    catalog = blog / "posts.json"
    entries = json.loads(catalog.read_text(encoding="utf-8")) if catalog.exists() else []
    digest = sha256(json.dumps(draft, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    existing = next((item for item in entries if item["slug"] == slug), None)
    if existing and article.is_file() and existing.get("digest") == digest:
        return SITE + blog_path(slug)
    if article.exists() or existing:
        raise ValueError("That article URL already exists. Choose a new URL slug.")
    published = datetime.now(ZoneInfo("Africa/Nairobi")).isoformat(timespec="seconds")
    entries.insert(0, {key: draft[key] for key in ("title", "slug", "description", "image", "alt")} |
                   {"published": published, "digest": digest})
    home = root / "index.html"
    homepage = home.read_text(encoding="utf-8")
    sitemap = root / "sitemap.xml"
    sitemap_text = sitemap.read_text(encoding="utf-8")
    if SITEMAP_MARKER not in sitemap_text or FOOTER_MARKER not in homepage:
        raise ValueError("The homepage or sitemap insertion point is missing.")
    if BLOG_LINK not in homepage:
        homepage = homepage.replace(FOOTER_MARKER, BLOG_LINK + "\n                    " + FOOTER_MARKER, 1)
    paths = ["/blog/", blog_path(slug)] if len(entries) == 1 else [blog_path(slug)]
    sitemap_entries = "".join(f"  <url><loc>{SITE}{path}</loc></url>\n" for path in paths)
    sitemap_text = sitemap_text.replace(SITEMAP_MARKER, sitemap_entries + SITEMAP_MARKER, 1)
    article_html = render_article(draft, published)
    index_html = render_index(entries)

    article.parent.mkdir(parents=True)
    article.write_text(article_html, encoding="utf-8")
    (blog / "index.html").write_text(index_html, encoding="utf-8")
    catalog.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    home.write_text(homepage, encoding="utf-8")
    sitemap.write_text(sitemap_text, encoding="utf-8")
    return SITE + blog_path(slug)


if __name__ == "__main__":
    try:
        address = publish(read_draft(os.environ.get("BLOG_PUBLISH_CODE")))
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
    print(address)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write(f"Article URL after GitHub Pages publishes the new commit: {address}\n")
