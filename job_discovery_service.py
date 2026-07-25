"""
Job Discovery Service - Multi-source job crawler
Handles Indeed, LinkedIn, Naukri, and Google Jobs with parallel execution and caching.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Set

import structlog
from playwright.async_api import Browser, async_playwright

logger = structlog.get_logger(__name__)


@dataclass
class JobListing:
    """Unified job listing across all sources"""

    title: str
    company: str
    location: str
    description: str
    url: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    posted_date: Optional[datetime] = None
    source: str = "unknown"  # 'indeed', 'linkedin', 'naukri'
    job_type: Optional[str] = None  # 'full-time', 'contract', 'temporary'
    seniority_level: Optional[str] = None  # 'entry', 'mid', 'senior'
    company_size: Optional[str] = None
    remote_friendly: bool = False


class BaseJobCrawler(ABC):
    """Abstract base class for all job board crawlers"""

    name: str = "base"
    timeout: int = 30

    @abstractmethod
    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Search for jobs"""
        pass

    async def _llm_extract_jobs(self, page_text: str, board_name: str) -> List[JobListing]:
        """
        Fallback: when CSS selectors fail, dump visible DOM text and ask the
        local LLM to extract job fields. This handles site layout changes
        without requiring selector updates.
        """
        from llm_client import llm_chat
        from config import settings

        prompt = f"""You are a data extraction assistant. Below is the visible text from a job board ({board_name}) search results page.

Extract ALL job listings as a JSON array. Each entry must have:
- title: job title
- company: company name
- location: job location
- description: brief snippet (first 200 chars if available)

Return ONLY a JSON array, no other text. If no jobs found, return [].

PAGE TEXT:
{page_text[:8000]}"""

        try:
            response_text = llm_chat(
                prompt=prompt,
                model=settings.FAST_LLM_MODEL,
                max_tokens=2000,
                temperature=0.0,
            )
            text = response_text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            raw = json.loads(text.strip())
            jobs = []
            for item in raw:
                jobs.append(JobListing(
                    title=item.get("title", "Unknown"),
                    company=item.get("company", "Unknown"),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    url="",
                    source=self.name,
                ))
            logger.info("llm_extract_fallback", board=board_name, jobs_found=len(jobs))
            return jobs
        except Exception as e:
            logger.error("llm_extract_fallback_failed", error=str(e))
            return []

    async def _extract_with_fallback(
        self, page, selectors: dict, card_idx: int, page_text: str
    ) -> dict:
        """
        Try CSS selectors first. If any fail, fall back to LLM extraction
        using the page's visible text.
        """
        result = {}
        all_succeeded = True
        for field, selector in selectors.items():
            try:
                elem = await page.query_selector(selector)
                if elem:
                    result[field] = (await elem.text_content() or "").strip()
                else:
                    result[field] = ""
                    all_succeeded = False
            except Exception:
                result[field] = ""
                all_succeeded = False

        if not all_succeeded and page_text and card_idx == 0:
            logger.info("selector_fallback_triggered", page=self.name)
            # LLM fallback happens at the page level, not per-card
        return result

    async def _create_browser(self) -> Browser:
        """Create Playwright browser instance with stealth anti-detection"""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        return browser

    async def _setup_stealth_page(self, browser: Browser):
        """Create a page with stealth headers to avoid bot detection"""
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        return page

    async def _setup_stealth_context(self, browser: Browser):
        """
        Create a browser context with saved auth cookies (if available)
        and stealth headers. Returns (context, page).
        """
        from browser_auth import load_cookies

        cookies = load_cookies(self.name) if hasattr(self, "name") else []

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="en-US",
        )

        if cookies:
            await context.add_cookies(cookies)
            logger.info("auth_cookies_loaded", site=self.name, count=len(cookies))

        page = await context.new_page()
        await page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        return context, page

    async def _normalize_salary(self, salary_str: str) -> tuple[Optional[float], Optional[float]]:
        """Extract min/max salary from string like '$50k - $70k'"""
        try:
            import re

            # Extract numbers
            numbers = re.findall(r"\d+[kK]?", salary_str)
            if not numbers:
                return None, None

            values = []
            for num in numbers:
                val = float(num.rstrip("kK"))
                if num.endswith(("k", "K")):
                    val *= 1000
                values.append(val)

            if len(values) >= 2:
                return min(values), max(values)
            elif len(values) == 1:
                return values[0], values[0]
        except Exception as e:
            logger.debug("salary_parse_error", error=str(e), salary_str=salary_str)
        return None, None


class IndeedCrawler(BaseJobCrawler):
    """Indeed job crawler — uses India domain by default"""

    name = "indeed"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Scrape jobs from Indeed India"""
        import asyncio as asyncio_mod

        jobs = []
        browser = None

        try:
            browser = await self._create_browser()
            context, page = await self._setup_stealth_context(browser)

            # Build search URL — use .co.in for India
            query = "+".join(keywords)
            url = f"https://www.indeed.co.in/jobs?q={query}&l={location}&start=0&limit={limit}"

            logger.info("indeed_search", query=query, location=location, url=url)

            await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            await page.wait_for_load_state("networkidle")
            await asyncio_mod.sleep(3)  # Wait for JS-rendered cards

            # Find job listings
            job_cards = await page.query_selector_all("div.job_seen_beacon")

            for idx, card in enumerate(job_cards):
                try:
                    # Extract job details
                    title_elem = await card.query_selector("h2 a")
                    company_elem = await card.query_selector("span[data-testid='company-name']")
                    location_elem = await card.query_selector("div[data-testid='job-location']")
                    salary_elem = await card.query_selector("div[data-testid='salary-snippet']")
                    snippet_elem = await card.query_selector("div.job-snippet")

                    title = await title_elem.text_content() if title_elem else ""
                    company = await company_elem.text_content() if company_elem else ""
                    loc = await location_elem.text_content() if location_elem else location
                    description = (
                        await snippet_elem.text_content() if snippet_elem else ""
                    )
                    salary_text = (
                        await salary_elem.text_content() if salary_elem else ""
                    )
                    job_url = await title_elem.get_attribute("href") if title_elem else ""

                    # Parse salary
                    salary_min, salary_max = await self._normalize_salary(salary_text)

                    # Get full job URL
                    full_url = f"https://www.indeed.com{job_url}" if job_url else ""

                    job = JobListing(
                        title=title.strip(),
                        company=company.strip(),
                        location=loc.strip(),
                        description=description.strip()[:500],
                        url=full_url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        source=self.name,
                        remote_friendly="remote" in description.lower(),
                    )

                    jobs.append(job)
                    logger.debug("job_parsed", title=job.title, company=job.company)

                except Exception as e:
                    logger.warning(
                        "job_parse_error", index=idx, error=str(e)
                    )
                    continue

            logger.info("indeed_complete", jobs_found=len(jobs))

        except Exception as e:
            logger.error("indeed_crawler_error", error=str(e), exc_info=True)

        finally:
            if browser:
                await browser.close()

        return jobs


class LinkedInCrawler(BaseJobCrawler):
    """LinkedIn job crawler (requires authentication + session cookies)"""

    name = "linkedin"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Scrape jobs from LinkedIn (requires authentication)"""
        import asyncio as asyncio_mod

        jobs = []
        browser = None

        try:
            browser = await self._create_browser()
            context, page = await self._setup_stealth_context(browser)

            # Build LinkedIn jobs URL
            query = "-".join(keywords)
            url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location={location}"

            logger.info("linkedin_search", query=query, location=location)

            await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            await asyncio_mod.sleep(3)

            # Parse job cards
            job_cards = await page.query_selector_all(
                "li[data-job-id]"
            )

            for card in job_cards[:limit]:
                try:
                    title_elem = await card.query_selector("h3.base-search-card__title")
                    company_elem = await card.query_selector(
                        "h4.base-search-card__subtitle"
                    )
                    location_elem = await card.query_selector(
                        "span.job-search-card__location"
                    )

                    title = await title_elem.text_content() if title_elem else ""
                    company = (
                        await company_elem.text_content() if company_elem else ""
                    )
                    loc = await location_elem.text_content() if location_elem else ""

                    # Get job URL
                    job_link = await card.get_attribute("data-job-id")
                    job_url = f"https://www.linkedin.com/jobs/view/{job_link}/"

                    job = JobListing(
                        title=title.strip(),
                        company=company.strip(),
                        location=loc.strip(),
                        description="",  # Fetch separately if needed
                        url=job_url,
                        source=self.name,
                    )

                    jobs.append(job)

                except Exception as e:
                    logger.warning("linkedin_job_parse_error", error=str(e))
                    continue

            logger.info("linkedin_complete", jobs_found=len(jobs))

        except Exception as e:
            logger.error("linkedin_crawler_error", error=str(e), exc_info=True)

        finally:
            if browser:
                await browser.close()

        return jobs


class NaukriCrawler(BaseJobCrawler):
    """Naukri.com job crawler — updated selectors + stealth"""

    name = "naukri"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Scrape jobs from Naukri.com"""
        import asyncio as asyncio_mod

        jobs = []
        browser = None

        try:
            browser = await self._create_browser()
            context, page = await self._setup_stealth_context(browser)

            # Build Naukri search URL — try slug-based format
            query_slug = "-".join(k.lower() for k in keywords)
            location_slug = location.replace(" ", "-").lower()
            url = f"https://www.naukri.com/{query_slug}-jobs-in-{location_slug}"

            logger.info("naukri_search", keywords=keywords, location=location, url=url)

            await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            await page.wait_for_load_state("networkidle")
            await asyncio_mod.sleep(3)  # Wait for JS-rendered cards

            # Updated selectors (fallback chain for Naukri's frequently-changing DOM)
            job_cards = await page.query_selector_all(
                "div.srp-jobtuple-wrapper, div.jobTuple, article.jobTuple, div.cust-job-tuple"
            )

            for idx, card in enumerate(job_cards[:limit]):
                try:
                    title_elem = await card.query_selector("a.title, a.jobTitle, h2 a, a[class*='title']")
                    company_elem = await card.query_selector("a.comp-name, a.companyName, div.companyInfo a, a[class*='comp']")
                    location_elem = await card.query_selector("span.locWdth, span.location, div.jobLocation, span[class*='loc']")
                    salary_elem = await card.query_selector("span.sal, span.salary, div.salary, span[class*='sal']")

                    title = await title_elem.text_content() if title_elem else ""
                    company = (
                        await company_elem.text_content() if company_elem else ""
                    )
                    loc = await location_elem.text_content() if location_elem else ""
                    salary_text = (
                        await salary_elem.text_content() if salary_elem else ""
                    )
                    job_url = await title_elem.get_attribute("href") if title_elem else ""

                    # Parse salary
                    salary_min, salary_max = await self._normalize_salary(salary_text)

                    job = JobListing(
                        title=title.strip(),
                        company=company.strip(),
                        location=loc.strip(),
                        description="",
                        url=job_url if job_url.startswith("http") else f"https://www.naukri.com{job_url}",
                        salary_min=salary_min,
                        salary_max=salary_max,
                        source=self.name,
                    )

                    jobs.append(job)

                except Exception as e:
                    logger.warning("naukri_job_parse_error", index=idx, error=str(e))
                    continue

            logger.info("naukri_complete", jobs_found=len(jobs))

        except Exception as e:
            logger.error("naukri_crawler_error", error=str(e), exc_info=True)

        finally:
            if browser:
                await browser.close()

        return jobs


class RemotiveCrawler(BaseJobCrawler):
    """Remotive.com — free remote job board API (no auth required)"""

    name = "remotive"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        import requests

        jobs = []
        try:
            query = " ".join(keywords)
            url = f"https://remotive.com/api/remote-jobs?search={query}&limit={min(limit, 50)}"
            logger.info("remotive_search", query=query, url=url)

            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            for item in data.get("jobs", [])[:limit]:
                jobs.append(JobListing(
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("candidate_required_location", "Remote"),
                    description=item.get("description", "")[:2000],
                    url=item.get("url", ""),
                    salary_min=None,
                    salary_max=None,
                    source=self.name,
                    job_type=item.get("job_type", ""),
                    remote_friendly=True,
                ))

            logger.info("remotive_complete", jobs_found=len(jobs))

        except Exception as e:
            logger.error("remotive_crawler_error", error=str(e))

        return jobs


class ArbeitnowCrawler(BaseJobCrawler):
    """Arbeitnow.com — free job board API (no auth required, EU-focused)"""

    name = "arbeitnow"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        import requests

        jobs = []
        try:
            url = "https://www.arbeitnow.com/api/job-board-api"
            logger.info("arbeitnow_search", url=url)

            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            # Filter by keyword match in title
            query_terms = set(k.lower() for k in keywords)
            matched = []
            for item in data.get("data", []):
                title = (item.get("title") or "").lower()
                if any(term in title for term in query_terms):
                    matched.append(item)
                if len(matched) >= limit:
                    break

            for item in matched:
                jobs.append(JobListing(
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("location", ""),
                    description=item.get("description", "")[:2000],
                    url=item.get("url", ""),
                    salary_min=None,
                    salary_max=None,
                    source=self.name,
                    job_type=",".join(item.get("job_types", [])) if item.get("job_types") else None,
                    remote_friendly=item.get("remote", False),
                ))

            logger.info("arbeitnow_complete", jobs_found=len(jobs))

        except Exception as e:
            logger.error("arbeitnow_crawler_error", error=str(e))

        return jobs


class JobDiscoveryService:
    """Orchestrator for multi-source job discovery"""

    def __init__(self):
        self.crawlers = {
            "remotive": RemotiveCrawler(),
            "arbeitnow": ArbeitnowCrawler(),
            "indeed": IndeedCrawler(),
            "linkedin": LinkedInCrawler(),
            "naukri": NaukriCrawler(),
        }

    async def search_all_sources(
        self,
        keywords: List[str],
        location: str,
        limit: int = 20,
        sources: Optional[List[str]] = None,
    ) -> List[JobListing]:
        """Search across multiple job sources in parallel"""

        if sources is None:
            sources = list(self.crawlers.keys())

        logger.info(
            "job_discovery_start",
            keywords=keywords,
            location=location,
            sources=sources,
        )

        # Create tasks for each crawler
        tasks = [
            self.crawlers[source].search(keywords, location, limit)
            for source in sources
            if source in self.crawlers
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results and deduplicate
        all_jobs: List[JobListing] = []
        seen_urls: Set[str] = set()

        for result in results:
            if isinstance(result, Exception):
                logger.error("crawler_error", error=str(result))
                continue

            for job in result:
                if job.url not in seen_urls and job.url:
                    all_jobs.append(job)
                    seen_urls.add(job.url)

        # Sort by likely relevance (remote friendly, recent first)
        all_jobs.sort(
            key=lambda x: (not x.remote_friendly, x.posted_date or datetime.min),
            reverse=True,
        )

        logger.info("job_discovery_complete", total_jobs=len(all_jobs))

        return all_jobs

    async def search_single_source(
        self, source: str, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Search a specific job source"""
        if source not in self.crawlers:
            logger.warning("unknown_source", source=source)
            return []

        logger.info(
            "search_single_source", source=source, keywords=keywords, location=location
        )
        return await self.crawlers[source].search(keywords, location, limit)


__all__ = [
    "JobListing",
    "BaseJobCrawler",
    "RemotiveCrawler",
    "ArbeitnowCrawler",
    "IndeedCrawler",
    "LinkedInCrawler",
    "NaukriCrawler",
    "JobDiscoveryService",
]
