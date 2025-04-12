import os
import re
import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor
import threading
import argparse

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create a lock for thread-safe operations
lock = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}

class WebsiteMirror:
    def __init__(self, base_url, output_dir, max_workers=5):
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.visited_urls = set()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def ensure_directory(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def get_local_path(self, url):
        parsed_url = urlparse(url)
        path = unquote(parsed_url.path.strip("/"))

        if not path:
            path = "index.html"
        elif path.endswith("/"):
            path += "index.html"
        elif not os.path.splitext(path)[1]:
            path += ".html"

        return os.path.join(self.output_dir, path)

    def save_resource(self, url, content):
        local_path = self.get_local_path(url)
        local_dir = os.path.dirname(local_path)

        with lock:
            self.ensure_directory(local_dir)

        with open(local_path, "wb") as f:
            f.write(content)

    def download_resource(self, url):
        try:
            response = self.session.get(url, timeout=10, verify=False)
            response.raise_for_status()
            self.save_resource(url, response.content)
            return response.text if "text/html" in response.headers.get("Content-Type", "") else None
        except Exception:
            print(f"Failed to download {url}: Connection error.")
            return None

    def rewrite_links(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(["a", "link", "script", "img"]):
            if tag.name in ["a", "link"] and tag.get("href"):
                tag["href"] = self.rewrite_url(tag["href"], base_url)
            elif tag.name in ["script", "img"] and tag.get("src"):
                tag["src"] = self.rewrite_url(tag["src"], base_url)

        return str(soup)

    def rewrite_url(self, url, base_url):
        full_url = urljoin(base_url, url)
        parsed_url = urlparse(full_url)
        path = unquote(parsed_url.path.strip("/"))

        if full_url.startswith(self.base_url):
            if path and not os.path.splitext(path)[1]:
                path += ".html"
            local_path = os.path.join(self.output_dir, path)
            return os.path.relpath(local_path, self.output_dir).replace("\\", "/")
        return url

    def extract_links(self, html, base_url):
        soup = BeautifulSoup(html, "html.parser")
        links = set()

        for tag in soup.find_all(["a", "link", "script", "img"]):
            if tag.name in ["a", "link"] and tag.get("href"):
                links.add(urljoin(base_url, tag["href"]))
            elif tag.name in ["script", "img"] and tag.get("src"):
                links.add(urljoin(base_url, tag["src"]))

        return links

    def mirror_page(self, url):
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)

        print(f"Mirroring: {url}")
        html = self.download_resource(url)
        if html:
            rewritten_html = self.rewrite_links(html, url)
            self.save_resource(url, rewritten_html.encode("utf-8"))

            links = self.extract_links(html, url)
            for link in links:
                if link.startswith(self.base_url) and link not in self.visited_urls:
                    self.executor.submit(self.mirror_page, link)

    def start_mirroring(self):
        self.mirror_page(self.base_url)
        self.executor.shutdown(wait=True)

def get_domain_name(url):
    return urlparse(url).netloc.replace("www.", "")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mirror a website to local files.")
    parser.add_argument("-d", "--domain", required=True, help="Website URL to mirror (e.g., https://example.com)")
    args = parser.parse_args()

    base_url = args.domain.strip()

    if not base_url.startswith("http"):
        print("Invalid URL. Please include 'http://' or 'https://'.")
        exit(1)

    output_dir = get_domain_name(base_url)

    mirror = WebsiteMirror(base_url, output_dir)
    mirror.start_mirroring()

    print("Mirroring completed!")
