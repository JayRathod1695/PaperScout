import asyncio
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org"


class OpenAlexClient:
    """OpenAlex API client with basic search and DOI lookup helpers."""

    def __init__(self) -> None:
        self.api_key = settings.openalex_api_key
        self.headers: dict[str, str] = {
            "User-Agent": "PaperScout/1.0 (research tool)",
        }

    async def search_papers(
        self,
        keywords: list[str],
        max_results: int = 8,
        year_min: Optional[int] = None,
        use_advanced_search: bool = True,
    ) -> list[dict]:
        """Search OpenAlex for papers matching the supplied keywords."""
        query = self._build_query(keywords, use_advanced_search)
        logger.info(f"OpenAlex query: '{query}'")

        params: dict[str, str | int] = {
            "search": query,
            "per-page": max_results + 5,
            "select": "id,title,authorships,publication_year,abstract_inverted_index,doi,cited_by_count,open_access",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        if year_min:
            params["filter"] = f"publication_year:>{year_min - 1}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{BASE_URL}/works", params=params, headers=self.headers)
            if response.status_code == 429:
                logger.warning("OpenAlex rate limit hit, retrying after 2 seconds")
                await asyncio.sleep(2)
                return await self.search_papers(keywords, max_results, year_min, use_advanced_search)
            response.raise_for_status()

        results = response.json().get("results", [])
        logger.info(f"OpenAlex returned {len(results)} raw results")

        seen_titles: set[str] = set()
        papers: list[dict] = []

        for work in results:
            title = work.get("title")
            if not title:
                continue

            title_key = title.lower().strip()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index") or {})
            if not abstract:
                continue

            authors = self._extract_authors(work.get("authorships") or [])
            doi = work.get("doi")
            url = f"https://doi.org/{doi}" if doi else work.get("id")

            papers.append(
                {
                    "title": title,
                    "authors": authors[:5],
                    "year": work.get("publication_year"),
                    "abstract": abstract,
                    "url": url,
                    "doi": doi,
                    "cited_by_count": work.get("cited_by_count", 0),
                    "open_access": (work.get("open_access") or {}).get("is_oa", False),
                    "work_id": work.get("id", ""),
                }
            )

            if len(papers) >= max_results:
                break

        logger.info(f"Returning {len(papers)} filtered papers from OpenAlex")
        return papers

    async def search_by_doi(self, doi: str) -> Optional[dict]:
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{BASE_URL}/works/doi/{doi}", params=params, headers=self.headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()

        work = response.json()
        authors = self._extract_authors(work.get("authorships") or [])

        return {
            "title": work.get("title"),
            "authors": authors[:5],
            "year": work.get("publication_year"),
            "abstract": self._reconstruct_abstract(work.get("abstract_inverted_index") or {}),
            "url": f"https://doi.org/{doi}",
            "doi": doi,
            "cited_by_count": work.get("cited_by_count", 0),
        }

    async def search_papers_multi_query(self, keyword_sets: list[list[str]], max_results: int = 8) -> list[dict]:
        """Run multiple OpenAlex searches and merge unique results."""
        all_papers: list[dict] = []
        seen_titles: set[str] = set()

        for keywords in keyword_sets:
            try:
                await asyncio.sleep(1)
                papers = await self.search_papers(keywords, max_results=max_results)
                for paper in papers:
                    title_key = paper["title"].lower().strip()
                    if title_key not in seen_titles:
                        seen_titles.add(title_key)
                        all_papers.append(paper)
            except Exception as exc:
                logger.warning(f"OpenAlex search failed for keywords {keywords}: {exc}")
                continue

            if len(all_papers) >= max_results:
                break

        return all_papers[:max_results]

    def _build_query(self, keywords: list[str], use_advanced_search: bool) -> str:
        if not use_advanced_search:
            return " ".join(keywords[:5])

        search_terms: list[str] = []
        for keyword in keywords[:5]:
            if " " in keyword:
                search_terms.append(f'"{keyword}"')
            else:
                search_terms.append(keyword)
        return " ".join(search_terms)

    def _extract_authors(self, authorships: list[dict]) -> list[str]:
        authors: list[str] = []
        for authorship in authorships:
            author = authorship.get("author") or {}
            display_name = author.get("display_name")
            if display_name:
                authors.append(display_name)
        return authors

    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        if not inverted_index:
            return ""

        positions: list[tuple[int, str]] = []
        for word, word_positions in inverted_index.items():
            for position in word_positions:
                positions.append((position, word))

        positions.sort(key=lambda item: item[0])
        return " ".join(word for _, word in positions)


async def search_papers(
    keywords: list[str],
    max_results: int = 8,
    year_min: Optional[int] = None,
) -> list[dict]:
    """Backward-compatible wrapper used by the search agent."""
    client = OpenAlexClient()
    return await client.search_papers(keywords, max_results=max_results, year_min=year_min)


async def search_papers_multi_query(keyword_sets: list[list[str]], max_results: int = 8) -> list[dict]:
    """Backward-compatible wrapper used by the search agent."""
    client = OpenAlexClient()
    return await client.search_papers_multi_query(keyword_sets, max_results=max_results)