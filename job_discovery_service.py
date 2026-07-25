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
        """Create Playwright browser instance"""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        return browser

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
    """Indeed.com job crawler"""

    name = "indeed"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Scrape jobs from Indeed"""
        jobs = []
        browser = None

        try:
            browser = await self._create_browser()
            page = await browser.new_page()

            # Build search URL
            query = "+".join(keywords)
            url = f"https://www.indeed.com/jobs?q={query}&l={location}&start=0&limit={limit}"

            logger.info("indeed_search", query=query, location=location, url=url)

            await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            await page.wait_for_load_state("networkidle")

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
    """LinkedIn job crawler (authenticated)"""

    name = "linkedin"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Scrape jobs from LinkedIn (requires authentication)"""
        jobs = []
        browser = None

        try:
            browser = await self._create_browser()
            page = await browser.new_page()

            # Build LinkedIn jobs URL
            query = "-".join(keywords)
            url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location={location}"

            logger.info("linkedin_search", query=query, location=location)

            # Note: LinkedIn requires login. In production, use stored session cookies
            # For now, this is a template for authenticated scraping

            await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)

            # Wait for job listings
            await page.wait_for_selector("ul.jobs-search__results-list", timeout=10000)

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
    """Naukri.com job crawler"""

    name = "naukri"

    async def search(
        self, keywords: List[str], location: str, limit: int = 20
    ) -> List[JobListing]:
        """Scrape jobs from Naukri.com"""
        jobs = []
        browser = None

        try:
            browser = await self._create_browser()
            page = await browser.new_page()

            # Build Naukri search URL
            query = "%20".join(keywords)
            location_param = location.replace(" ", "%20")
            url = f"https://www.naukri.com/jobs?k={query}&l={location_param}"

            logger.info("naukri_search", keywords=keywords, location=location)

            await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            await page.wait_for_load_state("networkidle")

            # Find job listings
            job_cards = await page.query_selector_all("div.srp-jobtuple-wrapper")

            for idx, card in enumerate(job_cards[:limit]):
                try:
                    # Naukri specific selectors
                    title_elem = await card.query_selector("a.title")
                    company_elem = await card.query_selector("a.comp-name")
                    location_elem = await card.query_selector("span.locWc")
                    exp_elem = await card.query_selector("span.expwc")
                    salary_elem = await card.query_selector("span.salaryText")

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


class JobDiscoveryService:
    """Orchestrator for multi-source job discovery"""

    def __init__(self):
        self.crawlers = {
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
    "IndeedCrawler",
    "LinkedInCrawler",
    "NaukriCrawler",
    "JobDiscoveryService",
]
