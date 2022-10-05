from bs4 import BeautifulSoup
from requests import Response
from requests.structures import CaseInsensitiveDict


class WebPage:
    def __init__(self, url: str, html: str, headers: CaseInsensitiveDict):
        self.url = url
        self.html = html
        self.headers = headers

        self._parse_html()

    def _parse_html(self):
        """
        Parse the HTML with BeautifulSoup to find <script> and <meta> tags.
        """
        self.parsed_html = soup = BeautifulSoup(self.html, 'lxml')
        self.scripts = [script['src'] for script in soup.findAll('script', src=True)]
        self.meta = {
            meta['name'].lower(): meta['content'] for meta in soup.findAll('meta', attrs=dict(name=True, content=True))
        }

    @classmethod
    def new_from_response(cls, response: Response):
        return cls(response.url, html=response.text, headers=response.headers)
