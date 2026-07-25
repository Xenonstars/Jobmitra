"""Application submission service using Playwright for automated form filling."""

import asyncio
import structlog
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, Page

from db.models import Job, Resume, Application
from config import settings
from job_discovery_service import JobListing

logger = structlog.get_logger(__name__)


class ApplicationSubmitter:
    """Handles automated job application submission via Playwright."""

    def __init__(self):
        self.headless = settings.HEADLESS_BROWSER
        self.timeout = settings.BROWSER_TIMEOUT * 1000
        self.slow_mo = settings.BROWSER_SLOWMO

    async def _launch_browser(self) -> tuple:
        """Launch Playwright browser with stealth settings."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        return playwright, browser, context

    async def apply_linkedin(
        self,
        job: Job,
        resume: Resume,
        cover_letter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply to a job on LinkedIn using Easy Apply."""

        logger.info("linkedin_apply_start", job_title=job.title, company=job.company)

        if not job.url or "linkedin.com" not in job.url:
            return {"status": "skipped", "reason": "Not a LinkedIn job URL"}

        try:
            playwright, browser, context = await self._launch_browser()
            page: Page = await context.new_page()

            await page.goto(job.url, wait_until="networkidle", timeout=self.timeout)
            await asyncio.sleep(2)

            # Click Easy Apply button
            easy_apply_btn = await page.query_selector(
                "button.jobs-apply-button, button[aria-label*='Easy Apply']"
            )
            if not easy_apply_btn:
                await browser.close()
                await playwright.stop()
                return {"status": "skipped", "reason": "No Easy Apply button found"}

            await easy_apply_btn.click()
            await asyncio.sleep(1)

            # Walk through multi-step form
            steps_completed = 0
            max_steps = 10

            while steps_completed < max_steps:
                # Try to fill current form fields
                await self._fill_form_fields(page, resume, cover_letter)

                # Click Next or Review
                next_btn = await page.query_selector(
                    "button[aria-label='Next'], button[aria-label='Review'], "
                    "button:has-text('Next'), button:has-text('Review')"
                )
                if next_btn:
                    await next_btn.click()
                    await asyncio.sleep(1)
                    steps_completed += 1
                else:
                    # Try Submit
                    submit_btn = await page.query_selector(
                        "button[aria-label='Submit application'], "
                        "button:has-text('Submit')"
                    )
                    if submit_btn:
                        await submit_btn.click()
                        await asyncio.sleep(2)
                        logger.info(
                            "linkedin_apply_success",
                            job_title=job.title,
                            company=job.company,
                        )
                        await browser.close()
                        await playwright.stop()
                        return {
                            "status": "submitted",
                            "platform": "linkedin",
                            "steps": steps_completed,
                        }
                    break

            await browser.close()
            await playwright.stop()
            return {
                "status": "submitted",
                "platform": "linkedin",
                "steps": steps_completed,
            }

        except Exception as e:
            logger.error("linkedin_apply_error", error=str(e), exc_info=True)
            return {"status": "failed", "reason": str(e)}

    async def apply_naukri(
        self,
        job: Job,
        resume: Resume,
        cover_letter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply to a job on Naukri.com."""

        logger.info("naukri_apply_start", job_title=job.title, company=job.company)

        if not job.url or "naukri.com" not in job.url:
            return {"status": "skipped", "reason": "Not a Naukri job URL"}

        try:
            playwright, browser, context = await self._launch_browser()
            page = await context.new_page()

            await page.goto(job.url, wait_until="networkidle", timeout=self.timeout)
            await asyncio.sleep(2)

            # Click Apply button
            apply_btn = await page.query_selector(
                "button.apply-button, a.apply-button, button:has-text('Apply')"
            )
            if not apply_btn:
                await browser.close()
                await playwright.stop()
                return {"status": "skipped", "reason": "No apply button found"}

            await apply_btn.click()
            await asyncio.sleep(2)

            # Fill form
            await self._fill_form_fields(page, resume, cover_letter)

            # Submit
            submit_btn = await page.query_selector(
                "button[type='submit'], button:has-text('Submit')"
            )
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(3)

            await browser.close()
            await playwright.stop()

            logger.info(
                "naukri_apply_success",
                job_title=job.title,
                company=job.company,
            )
            return {"status": "submitted", "platform": "naukri"}

        except Exception as e:
            logger.error("naukri_apply_error", error=str(e), exc_info=True)
            return {"status": "failed", "reason": str(e)}

    async def apply_generic(
        self,
        job: Job,
        resume: Resume,
        cover_letter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply via a generic career page form."""

        logger.info("generic_apply_start", job_title=job.title, company=job.company)

        try:
            playwright, browser, context = await self._launch_browser()
            page = await context.new_page()

            await page.goto(job.url, wait_until="networkidle", timeout=self.timeout)
            await asyncio.sleep(2)

            await self._fill_form_fields(page, resume, cover_letter)

            submit_btn = await page.query_selector(
                "button[type='submit'], input[type='submit'], button:has-text('Submit')"
            )
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(3)

            await browser.close()
            await playwright.stop()

            logger.info(
                "generic_apply_success",
                job_title=job.title,
                company=job.company,
            )
            return {"status": "submitted", "platform": "generic"}

        except Exception as e:
            logger.error("generic_apply_error", error=str(e), exc_info=True)
            return {"status": "failed", "reason": str(e)}

    async def _fill_form_fields(
        self, page: Page, resume: Resume, cover_letter: Optional[str] = None
    ):
        """Intelligently fill common application form fields."""

        # Resume upload
        file_inputs = await page.query_selector_all("input[type='file']")
        for fi in file_inputs:
            try:
                await fi.set_input_files(resume.filename)
            except Exception:
                pass

        # Cover letter / additional info text areas
        if cover_letter:
            textareas = await page.query_selector_all(
                "textarea[id*='cover'], textarea[name*='cover'], "
                "textarea[id*='additional'], textarea[name*='message']"
            )
            for ta in textareas:
                try:
                    await ta.fill(cover_letter)
                    break
                except Exception:
                    pass

        # Phone field
        if resume.parsed_data and resume.parsed_data.get("personal_information"):
            personal = resume.parsed_data["personal_information"]
            phone = personal.get("phone", "")
            phone_prefix = personal.get("phone_prefix", "")

            phone_inputs = await page.query_selector_all(
                "input[type='tel'], input[name*='phone'], input[id*='phone']"
            )
            for pi in phone_inputs:
                try:
                    await pi.fill(f"{phone_prefix}{phone}")
                except Exception:
                    pass

            # Email field
            email = personal.get("email", "")
            if email:
                email_inputs = await page.query_selector_all(
                    "input[type='email'], input[name*='email']"
                )
                for ei in email_inputs:
                    try:
                        await ei.fill(email)
                    except Exception:
                        pass

    async def submit_application(
        self,
        job: Job,
        resume: Resume,
        cover_letter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route to the correct platform-specific submitter."""

        url = job.url or ""
        source = job.source or ""

        if "linkedin.com" in url or source == "linkedin":
            return await self.apply_linkedin(job, resume, cover_letter)
        elif "naukri.com" in url or source == "naukri":
            return await self.apply_naukri(job, resume, cover_letter)
        else:
            return await self.apply_generic(job, resume, cover_letter)
