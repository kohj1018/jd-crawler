from src.parsers.base import BaseParser, JobItem
from src.parsers.generic import GenericParser

# Parser registry: maps parser_type to parser class (HTML-based parsers)
PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    "generic": GenericParser,
}

# API-based parsers are handled separately in crawler.py
# They don't inherit from BaseParser since they have their own crawling logic.
# Currently supported API parser types:
#   - "toss_job_groups_api": Toss job groups API (src/parsers/toss_job_groups_api.py)


def get_parser(parser_type: str, config: dict | None = None) -> BaseParser:
    """
    Get a parser instance by parser_type.

    Args:
        parser_type: The type of parser (e.g., 'generic', 'wanted', 'saramin')
        config: Optional parser-specific configuration from crawl_targets

    Returns:
        An instance of the appropriate parser

    Raises:
        ValueError: If parser_type is not registered

    To add a new parser:
        1. Create a new file in src/parsers/ (e.g., wanted.py)
        2. Implement a class that inherits from BaseParser
        3. Register it in PARSER_REGISTRY above

    Example:
        # src/parsers/wanted.py
        from src.parsers.base import BaseParser, JobItem

        class WantedParser(BaseParser):
            def parse_list(self, html: str) -> list[JobItem]:
                # Parse wanted.co.kr specific list HTML
                ...

            def parse_detail(self, html: str) -> str:
                # Parse wanted.co.kr specific detail HTML
                ...

        # Then in __init__.py:
        from src.parsers.wanted import WantedParser
        PARSER_REGISTRY["wanted"] = WantedParser
    """
    parser_class = PARSER_REGISTRY.get(parser_type)
    if parser_class is None:
        raise ValueError(
            f"Unknown parser_type: {parser_type}. "
            f"Available: {list(PARSER_REGISTRY.keys())}"
        )
    return parser_class(config or {})


__all__ = ["BaseParser", "JobItem", "get_parser", "PARSER_REGISTRY"]
