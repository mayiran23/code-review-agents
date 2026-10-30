import requests


def check_status(urls):
    result = {}
    for url in urls:
        resp = requests.get(url, timeout=5)
        result[url] = resp.status_code
    return result
