"""SEO issue detection and reporting"""
import threading
from fnmatch import fnmatch
from urllib.parse import urlparse
from difflib import SequenceMatcher


class IssueDetector:
    """Detects SEO and technical issues in crawled pages"""

    def __init__(self, exclusion_patterns=None):
        self.exclusion_patterns = exclusion_patterns or []
        self.detected_issues = []
        self.issues_lock = threading.Lock()

    def detect_issues(self, result):
        """Detect SEO issues for a crawled URL"""
        url = result.get('url', '')
        issues = []

        # Skip if URL matches exclusion patterns
        if self._should_exclude(url):
            return

        # Critical SEO Issues
        self._check_title_issues(result, issues)
        self._check_meta_description_issues(result, issues)
        self._check_heading_issues(result, issues)
        self._check_content_issues(result, issues)
        self._check_technical_issues(result, issues)
        self._check_mobile_issues(result, issues)
        self._check_accessibility_issues(result, issues)
        self._check_social_media_issues(result, issues)
        self._check_structured_data_issues(result, issues)
        self._check_performance_issues(result, issues)
        self._check_indexability_issues(result, issues)
        self._check_broken_image_issues(result, issues)

        # Add all detected issues
        with self.issues_lock:
            self.detected_issues.extend(issues)

    def _check_title_issues(self, result, issues):
        """Check for title-related issues"""
        url = result.get('url', '')
        title = result.get('title', '')

        if not title:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'SEO',
                'issue': 'Missing Title Tag',
                'details': 'Page has no title tag'
            })
        elif len(title) > 60:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'SEO',
                'issue': 'Title Too Long',
                'details': f"Title is {len(title)} characters (recommended: ≤60)"
            })
        elif len(title) < 30:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'SEO',
                'issue': 'Title Too Short',
                'details': f"Title is {len(title)} characters (recommended: 30-60)"
            })

    def _check_meta_description_issues(self, result, issues):
        """Check for meta description issues"""
        url = result.get('url', '')
        meta_desc = result.get('meta_description', '')

        if not meta_desc:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'SEO',
                'issue': 'Missing Meta Description',
                'details': 'Page has no meta description'
            })
        elif len(meta_desc) > 160:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'SEO',
                'issue': 'Meta Description Too Long',
                'details': f"Description is {len(meta_desc)} characters (recommended: ≤160)"
            })
        elif len(meta_desc) < 120:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'SEO',
                'issue': 'Meta Description Too Short',
                'details': f"Description is {len(meta_desc)} characters (recommended: 120-160)"
            })

    def _check_heading_issues(self, result, issues):
        """Check for heading-related issues"""
        url = result.get('url', '')

        if not result.get('h1'):
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'SEO',
                'issue': 'Missing H1 Tag',
                'details': 'Page has no H1 heading'
            })

    def _check_content_issues(self, result, issues):
        """Check for content-related issues"""
        url = result.get('url', '')
        word_count = result.get('word_count', 0)

        if word_count < 300:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Content',
                'issue': 'Thin Content',
                'details': f'Page has only {word_count} words (recommended: ≥300)'
            })

    def _check_technical_issues(self, result, issues):
        """Check for technical SEO issues"""
        url = result.get('url', '')
        status_code = result.get('status_code', 0)

        # No HTTP response at all (DNS failure, connection refused, timeout, etc.)
        if status_code == 0:
            error_type = result.get('error_type')
            error_label_map = {
                'dns_not_found': ('DNS Not Found',
                                  'Domain does not resolve. The site may be expired or misconfigured.'),
                'connection_refused': ('Connection Refused',
                                       'Server actively refused the connection.'),
                'timeout': ('Request Timeout',
                            'Server did not respond before the request timed out.'),
                'ssl_error': ('SSL/TLS Error',
                              'Could not establish a secure connection (certificate or TLS issue).'),
                'connection_error': ('Connection Error',
                                     'Could not connect to the server.'),
            }
            if error_type and error_type != 'file_too_large':
                title, default_details = error_label_map.get(
                    error_type, ('No Response', 'No HTTP response received.')
                )
                issues.append({
                    'url': url,
                    'type': 'error',
                    'category': 'Technical',
                    'issue': title,
                    'details': result.get('error') or default_details
                })

        if status_code >= 400 and status_code < 500:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Technical',
                'issue': f'{status_code} Client Error',
                'details': self._get_status_code_message(status_code)
            })
        elif status_code >= 500:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Technical',
                'issue': f'{status_code} Server Error',
                'details': self._get_status_code_message(status_code)
            })
        elif status_code >= 300 and status_code < 400:
            issues.append({
                'url': url,
                'type': 'info',
                'category': 'Technical',
                'issue': f'{status_code} Redirect',
                'details': 'URL redirects to another location'
            })

        # Canonical URL checks
        canonical_url = result.get('canonical_url', '')
        if not canonical_url:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Technical',
                'issue': 'Missing Canonical URL',
                'details': 'Page has no canonical URL specified'
            })
        elif canonical_url != url:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Technical',
                'issue': 'Canonical URL Different',
                'details': f"Canonical points to: {canonical_url}"
            })

    def _check_mobile_issues(self, result, issues):
        """Check for mobile optimization issues"""
        url = result.get('url', '')

        if not result.get('viewport'):
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Mobile',
                'issue': 'Missing Viewport Meta Tag',
                'details': 'Page is not mobile-optimized'
            })

    def _check_accessibility_issues(self, result, issues):
        """Check for accessibility issues"""
        url = result.get('url', '')

        if not result.get('lang'):
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Accessibility',
                'issue': 'Missing Language Attribute',
                'details': 'HTML tag has no lang attribute'
            })

        # Image alt text
        images = result.get('images', [])
        images_without_alt = [img for img in images if not img.get('alt')]
        if images_without_alt:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Accessibility',
                'issue': 'Images Without Alt Text',
                'details': f'{len(images_without_alt)} of {len(images)} images lack alt text'
            })

    def _check_social_media_issues(self, result, issues):
        """Check for social media optimization issues"""
        url = result.get('url', '')

        if not result.get('og_tags'):
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Social',
                'issue': 'Missing OpenGraph Tags',
                'details': 'Page has no OpenGraph tags for social sharing'
            })

        if not result.get('twitter_tags'):
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Social',
                'issue': 'Missing Twitter Card Tags',
                'details': 'Page has no Twitter Card tags'
            })

    def _check_structured_data_issues(self, result, issues):
        """Check for structured data issues"""
        url = result.get('url', '')

        if not result.get('json_ld') and not result.get('schema_org'):
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Structured Data',
                'issue': 'No Structured Data',
                'details': 'Page has no JSON-LD or Schema.org markup'
            })

    def _check_performance_issues(self, result, issues):
        """Check for performance issues"""
        url = result.get('url', '')
        response_time = result.get('response_time', 0)
        page_size = result.get('size', 0)

        if response_time > 3000:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Performance',
                'issue': 'Slow Response Time',
                'details': f'Page took {response_time}ms to respond (recommended: <3000ms)'
            })
        elif response_time > 1000:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Performance',
                'issue': 'Moderate Response Time',
                'details': f'Page took {response_time}ms to respond (recommended: <1000ms)'
            })

        if page_size > 3 * 1024 * 1024:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Performance',
                'issue': 'Large Page Size',
                'details': f'Page size is {page_size / 1024 / 1024:.1f}MB (recommended: <3MB)'
            })
        elif page_size > 1 * 1024 * 1024:
            issues.append({
                'url': url,
                'type': 'warning',
                'category': 'Performance',
                'issue': 'Moderate Page Size',
                'details': f'Page size is {page_size / 1024 / 1024:.1f}MB (recommended: <1MB)'
            })

    def _check_indexability_issues(self, result, issues):
        """Check for indexability issues"""
        url = result.get('url', '')
        robots = result.get('robots', '').lower()

        if 'noindex' in robots:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Indexability',
                'issue': 'Noindex Tag Present',
                'details': 'Page is BLOCKED from search engines - has noindex directive'
            })

        if 'nofollow' in robots:
            issues.append({
                'url': url,
                'type': 'error',
                'category': 'Indexability',
                'issue': 'Nofollow Tag Present',
                'details': 'Links on this page are NOT followed by search engines - has nofollow directive'
            })

    def _check_broken_image_issues(self, result, issues):
        """Check for broken image URLs on the page"""
        url = result.get('url', '')
        broken_images = result.get('broken_images', [])
        for img in broken_images:
            status = img.get('status', 0)
            img_url = img.get('url', '')
            if status == 0:
                issues.append({
                    'url': url,
                    'type': 'error',
                    'category': 'Content',
                    'issue': 'Broken Image (No Response)',
                    'details': f'Image does not respond: {img_url}'
                })
            elif status >= 400:
                issues.append({
                    'url': url,
                    'type': 'error',
                    'category': 'Content',
                    'issue': f'Broken Image ({status})',
                    'details': f'Image returned {status}: {img_url}'
                })

    def detect_duplication_issues(self, all_results, similarity_threshold=0.85,
                                  exact_limit=1000, window=20):
        """
        Detect content duplication across all crawled pages.

        For small crawls every page pair is compared directly. An exhaustive
        comparison is O(n^2) - for tens of thousands of pages that is hundreds
        of millions of comparisons (days of work) and the list of seen pairs
        alone would exhaust memory. So for large crawls candidate pairs are
        generated with the Sorted Neighborhood Method: pages are sorted by a
        normalised title key and again by a normalised description key, and
        only pages within a small sliding window of each other are compared.
        A pair can only reach the default 0.85 threshold when both its titles
        and its descriptions are highly similar (title and description each
        carry 0.35 of the score), so this catches real duplicates while
        keeping the work roughly linear in the number of pages.

        Args:
            all_results: List of all crawled result dictionaries
            similarity_threshold: Minimum similarity ratio to flag as duplicate (0.0-1.0)
            exact_limit: Crawls with at most this many pages use an exhaustive
                comparison; larger crawls use blocking.
            window: Sliding window size for the Sorted Neighborhood Method.
        """
        # Build a normalised signature for every page once, so the expensive
        # string normalisation is not repeated for every comparison.
        pages = []
        for result in all_results:
            url = result.get('url', '')
            if self._should_exclude(url):
                continue
            pages.append({
                'url': url,
                'title': (result.get('title') or '').lower().strip(),
                'desc': (result.get('meta_description') or '').lower().strip(),
                'h1': (result.get('h1') or '').lower().strip(),
                'word_count': result.get('word_count', 0) or 0,
            })

        n = len(pages)
        if n < 2:
            return

        if n <= exact_limit:
            candidate_pairs = (
                (i, j) for i in range(n) for j in range(i + 1, n)
            )
        else:
            candidate_pairs = self._duplication_candidate_pairs(pages, window)

        issues = []
        for i, j in candidate_pairs:
            similarity = self._calculate_signature_similarity(pages[i], pages[j])
            if similarity >= similarity_threshold:
                page_i, page_j = pages[i], pages[j]
                issues.append({
                    'url': page_i['url'],
                    'type': 'warning',
                    'category': 'Duplication',
                    'issue': 'Duplicate Content Detected',
                    'details': f"Content is {similarity*100:.1f}% similar to {page_j['url']}"
                })
                issues.append({
                    'url': page_j['url'],
                    'type': 'warning',
                    'category': 'Duplication',
                    'issue': 'Duplicate Content Detected',
                    'details': f"Content is {similarity*100:.1f}% similar to {page_i['url']}"
                })

        # Add all detected duplication issues
        with self.issues_lock:
            self.detected_issues.extend(issues)

    def _duplication_candidate_pairs(self, pages, window):
        """
        Generate candidate duplicate pairs for a large crawl using the Sorted
        Neighborhood Method. Pages are sorted by a normalised title key and by
        a normalised description key; within each ordering, every page is
        paired with the next `window` pages. Returns a set of (i, j) index
        pairs with i < j.
        """
        n = len(pages)
        candidates = set()
        for field in ('title', 'desc'):
            order = sorted(
                range(n),
                key=lambda idx: self._blocking_key(pages[idx][field])
            )
            for a in range(n):
                for b in range(a + 1, min(a + 1 + window, n)):
                    i, j = order[a], order[b]
                    if i == j:
                        continue
                    candidates.add((i, j) if i < j else (j, i))
        return candidates

    @staticmethod
    def _blocking_key(text):
        """
        Build a blocking key that is stable under word reordering, so pages
        whose title/description differ only in word order still sort next to
        each other.
        """
        return ' '.join(sorted(text.split()))

    def _calculate_signature_similarity(self, sig1, sig2):
        """
        Calculate similarity between two pre-normalised page signatures.

        Compares title, meta description, h1, and content length using a
        weighted average; title and description are the most important.
        Returns a similarity ratio between 0.0 and 1.0.
        """
        title1, title2 = sig1['title'], sig2['title']
        desc1, desc2 = sig1['desc'], sig2['desc']
        h1_1, h1_2 = sig1['h1'], sig2['h1']

        title_sim = self._text_similarity(title1, title2) if title1 and title2 else 0
        desc_sim = self._text_similarity(desc1, desc2) if desc1 and desc2 else 0
        h1_sim = self._text_similarity(h1_1, h1_2) if h1_1 and h1_2 else 0

        # Word count similarity (1.0 when the two counts are equal)
        word_count1, word_count2 = sig1['word_count'], sig2['word_count']
        if word_count1 and word_count2:
            max_count = max(word_count1, word_count2)
            min_count = min(word_count1, word_count2)
            word_count_sim = min_count / max_count if max_count > 0 else 0
        else:
            word_count_sim = 0

        # Weighted average (title and description are most important)
        return (
            title_sim * 0.35 +
            desc_sim * 0.35 +
            h1_sim * 0.20 +
            word_count_sim * 0.10
        )

    def _text_similarity(self, text1, text2):
        """Calculate similarity ratio between two text strings using SequenceMatcher"""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1, text2).ratio()

    def _should_exclude(self, url):
        """Check if URL should be excluded from issue detection"""
        parsed = urlparse(url)
        path = parsed.path

        for pattern in self.exclusion_patterns:
            if '*' in pattern:
                if fnmatch(path, pattern):
                    return True
            elif path == pattern or path.startswith(pattern.rstrip('*')):
                return True

        return False

    def _get_status_code_message(self, status_code):
        """Get descriptive message for HTTP status codes"""
        messages = {
            400: 'Bad Request',
            401: 'Unauthorized',
            403: 'Forbidden',
            404: 'Not Found',
            405: 'Method Not Allowed',
            406: 'Not Acceptable',
            408: 'Request Timeout',
            410: 'Gone',
            429: 'Too Many Requests',
            500: 'Internal Server Error',
            501: 'Not Implemented',
            502: 'Bad Gateway',
            503: 'Service Unavailable',
            504: 'Gateway Timeout',
            505: 'HTTP Version Not Supported'
        }
        return messages.get(status_code, f'HTTP {status_code} Error')

    def get_issues(self):
        """Get all detected issues"""
        with self.issues_lock:
            return self.detected_issues.copy()

    def reset(self):
        """Reset detected issues"""
        with self.issues_lock:
            self.detected_issues.clear()
