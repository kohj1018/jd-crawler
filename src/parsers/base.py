from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class JobItem:
    """Represents a job posting item extracted from a list page."""
    title: str
    url: str
    company_name: str = ""


class BaseParser(ABC):
    """
    Abstract base class for all parsers.

    Each parser handles a specific site or format.
    Subclasses must implement parse_list and parse_detail methods.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the parser with optional configuration.

        Args:
            config: Parser-specific configuration (e.g., CSS selectors)
                   This can come from the crawl_targets.parser_config column
        """
        self.config = config or {}

    @abstractmethod
    def parse_list(self, html: str) -> list[JobItem]:
        """
        Parse a job listing page and extract job items.

        Args:
            html: Raw HTML content of the list page

        Returns:
            List of JobItem objects with title, url, and company_name
        """
        pass

    @abstractmethod
    def parse_detail(self, html: str) -> str:
        """
        Parse a job detail page and extract the content.

        Args:
            html: Raw HTML content of the detail page

        Returns:
            Extracted text content (content_raw)
        """
        pass

    def normalize_html(self, html: str) -> str:
        """
        Normalize HTML for consistent hashing.

        Removes dynamic elements like timestamps, session IDs, etc.
        Subclasses can override this for site-specific normalization.

        Args:
            html: Raw HTML content

        Returns:
            Normalized HTML string
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        # Remove script and style tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # Remove comments
        from bs4 import Comment
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove common dynamic attributes
        for tag in soup.find_all(True):
            for attr in list(tag.attrs.keys()):
                if attr in ("data-timestamp", "data-session", "data-nonce", "data-csrf"):
                    del tag[attr]

        return str(soup)
