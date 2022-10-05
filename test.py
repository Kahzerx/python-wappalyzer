import requests

from wappalyzer.wappalyzer import Wappalyzer
from wappalyzer.web_page import WebPage

if __name__ == '__main__':
    page = WebPage.new_from_response(requests.get("https://www.google.com/"))
    print(Wappalyzer.latest().analyze_with_versions(page))
