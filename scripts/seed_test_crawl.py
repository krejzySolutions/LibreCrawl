"""
Seed script: inserts a synthetic 50,000-page completed crawl into the SQLite DB.

Usage (from repo root):
    python scripts/seed_test_crawl.py

Idempotent: a previous seed crawl for https://seed-50k.test is deleted and
re-created on every run. Useful for resetting to a clean state.
"""

import sys
import os
import json
import random
import sqlite3
from datetime import datetime, timedelta

# Allow `from src.crawl_db import ...` when run from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crawl_db import get_db, init_crawl_tables

# ── Constants ────────────────────────────────────────────────────────────────

BASE_URL    = 'https://seed-50k.test'
SESSION_ID  = 'seed-session'
NUM_URLS    = 50_000
LINKS_PER_PAGE = 4          # ~200 000 links total
NUM_ISSUES  = 5_000
BATCH_SIZE  = 5_000

# ── Helpers ───────────────────────────────────────────────────────────────────

def page_url(n: int) -> str:
    return f'{BASE_URL}/page-{n:05d}'

ISSUE_TYPES      = ['error', 'warning', 'info']
ISSUE_CATEGORIES = ['title', 'meta', 'headings', 'links', 'images', 'performance', 'redirects']
ISSUE_TEXTS = [
    'Missing meta description',
    'Title tag too long (>60 chars)',
    'Missing H1 tag',
    'Multiple H1 tags found',
    'Broken internal link',
    'Image missing alt attribute',
    'Slow response time (>3s)',
    'Non-canonical URL receiving links',
    'Redirect chain detected',
    '404 page linked from site',
    'Duplicate title tag',
    'Low word count (<300 words)',
]
PLACEMENTS = ['body', 'nav', 'footer', 'header', 'sidebar']
CONTENT_TYPES = ['text/html; charset=utf-8', 'text/html', 'application/xhtml+xml']

# Weighted status codes: 90 % 200, 5 % 301, 3 % 404, 2 % 500
STATUS_WEIGHTS = [200] * 90 + [301] * 5 + [404] * 3 + [500] * 2


def build_url_row(crawl_id: int, n: int) -> tuple:
    url         = page_url(n)
    status_code = random.choice(STATUS_WEIGHTS)
    depth       = random.randint(0, 5)
    size        = random.randint(4_000, 120_000)
    resp_time   = round(random.uniform(0.05, 4.5), 3)
    word_count  = random.randint(50, 2_500)
    is_internal = 1
    js_rendered = 0
    error_type  = None if status_code == 200 else ('timeout' if status_code == 500 else None)

    title = f'Page {n:05d} – Seed Crawl Test Site' if status_code == 200 else None
    meta_desc = f'This is the meta description for seed page {n}.' if status_code == 200 else None
    h1 = f'Welcome to page {n}' if status_code == 200 else None

    return (
        crawl_id,
        url,
        status_code,
        random.choice(CONTENT_TYPES),   # content_type
        size,
        is_internal,
        depth,
        title,
        meta_desc,
        h1,
        '[]',                           # h2
        '[]',                           # h3
        word_count,
        None,                           # canonical_url
        'en',                           # lang
        'utf-8',                        # charset
        'width=device-width',           # viewport
        'index, follow',                # robots
        '{}',                           # meta_tags
        '{}',                           # og_tags
        '{}',                           # twitter_tags
        '[]',                           # json_ld
        '{}',                           # analytics
        '[]',                           # images
        '[]',                           # hreflang
        '[]',                           # schema_org
        '[]',                           # redirects
        '[]',                           # linked_from
        random.randint(0, 30),          # external_links
        random.randint(0, 100),         # internal_links
        resp_time,
        js_rendered,
        error_type,
    )


def build_link_row(crawl_id: int, source_n: int) -> tuple:
    target_n    = random.randint(1, NUM_URLS)
    is_internal = 1 if random.random() < 0.85 else 0
    target_url  = page_url(target_n) if is_internal else f'https://external-{target_n % 50}.example/ref'
    target_dom  = BASE_URL.replace('https://', '') if is_internal else f'external-{target_n % 50}.example'
    target_st   = random.choice([200, 200, 200, 301, 404])
    placement   = random.choice(PLACEMENTS)
    anchor      = f'Link to page {target_n}'

    return (
        crawl_id,
        page_url(source_n),
        target_url,
        anchor,
        is_internal,
        target_dom,
        target_st,
        placement,
    )


def build_issue_row(crawl_id: int, n: int) -> tuple:
    url       = page_url(random.randint(1, NUM_URLS))
    issue_txt = random.choice(ISSUE_TEXTS)
    return (
        crawl_id,
        url,
        random.choice(ISSUE_TYPES),
        random.choice(ISSUE_CATEGORIES),
        issue_txt,
        f'Detected on page {n}: {issue_txt}',
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('Initialising crawl tables …')
    init_crawl_tables()

    now     = datetime.utcnow()
    started = now - timedelta(hours=2)

    with get_db() as conn:
        cursor = conn.cursor()

        # ── Idempotency: remove existing seed crawl ───────────────────────
        row = cursor.execute(
            'SELECT id FROM crawls WHERE base_url = ?', (BASE_URL,)
        ).fetchone()

        if row:
            old_id = row['id']
            print(f'Found existing seed crawl id={old_id}; removing …')
            # Always do manual cascade — avoids dependency on users table FK
            for tbl in ('crawled_urls', 'crawl_links', 'crawl_issues', 'crawl_queue'):
                cursor.execute(f'DELETE FROM {tbl} WHERE crawl_id = ?', (old_id,))
            cursor.execute('DELETE FROM crawls WHERE id = ?', (old_id,))

        # ── Owner: attach to the 'local' user so it shows in the dashboard ─
        # (the dashboard lists crawls filtered by the logged-in user_id).
        # Fall back to the first user, then to NULL (guest crawl).
        owner = cursor.execute(
            "SELECT id FROM users WHERE username = 'local'"
        ).fetchone()
        if owner is None:
            owner = cursor.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchone()
        owner_id = owner['id'] if owner else None
        print(f'Assigning seed crawl to user_id={owner_id}')

        # ── Insert crawls row ─────────────────────────────────────────────
        cursor.execute('''
            INSERT INTO crawls (
                user_id, session_id, base_url, base_domain,
                status, config_snapshot,
                urls_discovered, urls_crawled, max_depth_reached,
                started_at, completed_at, last_saved_at,
                peak_memory_mb, estimated_size_mb,
                can_resume, resume_checkpoint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            owner_id,       # user_id  — owner ('local' user in --local mode)
            SESSION_ID,
            BASE_URL,
            'seed-50k.test',
            'completed',
            '{}',           # config_snapshot
            NUM_URLS,       # urls_discovered
            NUM_URLS,       # urls_crawled
            5,              # max_depth_reached
            started.strftime('%Y-%m-%d %H:%M:%S'),
            now.strftime('%Y-%m-%d %H:%M:%S'),
            now.strftime('%Y-%m-%d %H:%M:%S'),
            512.0,          # peak_memory_mb
            256.0,          # estimated_size_mb
            0,              # can_resume
            None,           # resume_checkpoint
        ))

        crawl_id = cursor.lastrowid
        print(f'Created crawl row: id={crawl_id}')

    # ── crawled_urls ──────────────────────────────────────────────────────────
    print(f'Inserting {NUM_URLS:,} crawled_urls in batches of {BATCH_SIZE:,} …')
    total_urls = 0

    for batch_start in range(1, NUM_URLS + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, NUM_URLS)
        rows = [build_url_row(crawl_id, n) for n in range(batch_start, batch_end + 1)]

        with get_db() as conn:
            conn.executemany('''
                INSERT INTO crawled_urls (
                    crawl_id, url, status_code, content_type, size, is_internal, depth,
                    title, meta_description, h1, h2, h3, word_count,
                    canonical_url, lang, charset, viewport, robots,
                    meta_tags, og_tags, twitter_tags, json_ld, analytics, images,
                    hreflang, schema_org, redirects, linked_from,
                    external_links, internal_links, response_time, javascript_rendered,
                    error_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', rows)

        total_urls += len(rows)
        print(f'  urls: {total_urls:,} / {NUM_URLS:,}')

    # ── crawl_links ───────────────────────────────────────────────────────────
    total_links_target = NUM_URLS * LINKS_PER_PAGE
    print(f'Inserting ~{total_links_target:,} crawl_links in batches of {BATCH_SIZE:,} …')
    total_links = 0
    link_batch  = []

    for n in range(1, NUM_URLS + 1):
        for _ in range(LINKS_PER_PAGE):
            link_batch.append(build_link_row(crawl_id, n))

        if len(link_batch) >= BATCH_SIZE:
            with get_db() as conn:
                conn.executemany('''
                    INSERT INTO crawl_links (
                        crawl_id, source_url, target_url, anchor_text,
                        is_internal, target_domain, target_status, placement
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', link_batch)
            total_links += len(link_batch)
            print(f'  links: {total_links:,}')
            link_batch = []

    if link_batch:
        with get_db() as conn:
            conn.executemany('''
                INSERT INTO crawl_links (
                    crawl_id, source_url, target_url, anchor_text,
                    is_internal, target_domain, target_status, placement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', link_batch)
        total_links += len(link_batch)
        print(f'  links: {total_links:,}')

    # ── crawl_issues ──────────────────────────────────────────────────────────
    print(f'Inserting {NUM_ISSUES:,} crawl_issues …')
    issue_rows = [build_issue_row(crawl_id, n) for n in range(1, NUM_ISSUES + 1)]

    for i in range(0, len(issue_rows), BATCH_SIZE):
        chunk = issue_rows[i:i + BATCH_SIZE]
        with get_db() as conn:
            conn.executemany('''
                INSERT INTO crawl_issues (
                    crawl_id, url, type, category, issue, details
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', chunk)
        print(f'  issues: {min(i + BATCH_SIZE, NUM_ISSUES):,} / {NUM_ISSUES:,}')

    # ── Done ──────────────────────────────────────────────────────────────────
    print()
    print(f'Seeded crawl_id={crawl_id} ({total_urls:,} urls, {total_links:,} links, {NUM_ISSUES:,} issues)')


if __name__ == '__main__':
    main()
