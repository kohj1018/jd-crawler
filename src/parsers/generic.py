from bs4 import BeautifulSoup
from urllib.parse import urljoin

from src.parsers.base import BaseParser, JobItem


class GenericParser(BaseParser):
    """
    Generic parser using configurable CSS selectors.

    Expected config structure:
    {
        "list_selector": "CSS selector for job list items",
        "title_selector": "CSS selector for title within each item",
        "link_selector": "CSS selector for link within each item (optional, defaults to 'a')",
        "company_selector": "CSS selector for company name within each item (optional)",
        "detail_selector": "CSS selector for main content on detail page",
        "base_url": "Base URL for resolving relative links (optional)"
    }

    Example config for a typical job board:
    {
        "list_selector": ".job-list .job-item",
        "title_selector": ".job-title",
        "link_selector": "a.job-link",
        "company_selector": ".company-name",
        "detail_selector": ".job-description",
        "base_url": "https://example.com"
    }
    """

    def parse_list(self, html: str) -> list[JobItem]:
        """Parse job listings using configured selectors."""
        soup = BeautifulSoup(html, "lxml")
        items: list[JobItem] = []

        list_selector = self.config.get("list_selector", ".job-item")
        title_selector = self.config.get("title_selector", ".title")
        link_selector = self.config.get("link_selector", "a")
        company_selector = self.config.get("company_selector")
        base_url = self.config.get("base_url", "")

        job_elements = soup.select(list_selector)

        for element in job_elements:
            # Extract title
            title_el = element.select_one(title_selector)
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            # Extract link
            link_el = element.select_one(link_selector)
            if not link_el:
                # Try the element itself if it's a link
                link_el = element if element.name == "a" else None
            if not link_el:
                continue

            href = link_el.get("href", "")
            if not href:
                continue

            # Resolve relative URL
            url = urljoin(base_url, href) if base_url else href

            # Extract company name (optional)
            company_name = ""
            if company_selector:
                company_el = element.select_one(company_selector)
                if company_el:
                    company_name = company_el.get_text(strip=True)

            items.append(JobItem(title=title, url=url, company_name=company_name))

        return items

    def parse_detail(self, html: str) -> str:
        """Parse job detail page using configured selector."""
        soup = BeautifulSoup(html, "lxml")

        detail_selector = self.config.get("detail_selector", "main")

        content_el = soup.select_one(detail_selector)
        if content_el:
            # Remove script/style tags from content
            for tag in content_el(["script", "style"]):
                tag.decompose()
            return content_el.get_text(separator="\n", strip=True)

        # Fallback: try common content selectors
        fallback_selectors = [
            "article",
            ".job-description",
            ".job-content",
            ".content",
            "#content",
            "main",
        ]
        for selector in fallback_selectors:
            content_el = soup.select_one(selector)
            if content_el:
                for tag in content_el(["script", "style"]):
                    tag.decompose()
                return content_el.get_text(separator="\n", strip=True)

        # Last resort: body text
        body = soup.find("body")
        if body:
            for tag in body(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            return body.get_text(separator="\n", strip=True)

        return ""
