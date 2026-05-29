import aiohttp
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

logging.basicConfig(level=logging.INFO)

class BaseFetcher(ABC):
    TIMEOUT = aiohttp.ClientTimeout(total=30)
    HEADERS = {"User-Agent": "meta-generator/1.0 (github.com/waxbyz/mcorefetcher)"}

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.TIMEOUT,
                headers=self.HEADERS
            )
        return self._session
    
    async def get(self, url: str, retries: int = 3) -> Optional[str]:
        session = await self._get_session()
        for attempt in range(retries):
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logging.error(f"Failed to GET {url}, status={resp.status}")
                        return None
                    return await resp.text()
            except Exception as e:
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    logging.warning(f"Retrying {url} in {wait}s (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(wait)
                else:
                    logging.error(f"Request failed after {retries} attempts: {e}")
                    return None
        
    async def get_json(self, url) -> Optional[dict | list]:
        import json
        text = await self.get(url)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON for {url}: {e}")

    async def head(self, url: str) -> Optional[dict]:
        session = await self._get_session()
        for attempt in range(3):
            try:
                async with session.head(url) as resp:
                    if resp.status != 200:
                        return None
                    return dict(resp.headers)
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logging.error(f"HEAD request failed: {e}")
                    return None

    async def close(self):
        logging.info('Closing session')
        if self._session and not self._session.closed:
            await self._session.close()
    
#Interface
@property
@abstractmethod
def platform_id(self) -> str:
    pass

@property
@abstractmethod
def platform_name(self) -> str:
    pass

@property
@abstractmethod
def platform_uid(self) -> str:
    pass

@abstractmethod
async def fetch(self) -> list[str]:
    pass