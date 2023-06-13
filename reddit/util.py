import time
from logging import Logger
from pathlib import Path

import orjson
from httpx import Response

BLACK = "\x1b[30m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
WHITE = "\x1b[37m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s.%(msecs)03d [%(levelname)s] :: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout',
        },
        'file': {
            'class': 'logging.FileHandler',
            'level': 'DEBUG',
            'formatter': 'standard',
            'filename': 'reddit.log',
            'mode': 'a',
        },
    },
    'loggers': {
        'reddit': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        }
    }
}


def get_rate_limits(r: Response) -> dict:
    return {
        k: v
        for k, v in r.headers.items()
        if k in {"x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-used"}
    }


def find_key(obj: any, key: str) -> list:
    """
    Find all values of a given key within a nested dict or list of dicts

    @param obj: dictionary or list of dictionaries
    @param key: key to search for
    @return: list of values
    """

    def helper(obj: any, key: str, L: list) -> list:
        if not obj:
            return L

        if isinstance(obj, list):
            for e in obj:
                L.extend(helper(e, key, []))
            return L

        if isinstance(obj, dict) and obj.get(key):
            L.append(obj[key])

        if isinstance(obj, dict) and obj:
            for k in obj:
                L.extend(helper(obj[k], key, []))
        return L

    return helper(obj, key, [])


def extract_json(text: str) -> dict | None:
    count = 0
    chars = []
    for c in text:
        if c == "{":
            count += 1
        if count > 0:
            chars.append(c)
        if c == "}":
            count -= 1
            if count == 0:
                try:
                    return orjson.loads("".join(chars))
                except orjson.JSONDecodeError:
                    ...


def log(logger: Logger, level: int, r: Response):
    def stat(r, txt, data):
        if level >= 1:
            logger.debug(f'{r.url.path}')
        if level >= 2:
            logger.debug(f'{r.url}')
        if level >= 3:
            logger.debug(f'payload = {r.request.content}')
        if level >= 4:
            logger.debug(f'headers = {dict(r.request.headers)}')
        if level >= 5:
            logger.debug(f'(Response) cookies = {dict(r.cookies)}')
        if level >= 6:
            logger.debug(f'(Response) text = {txt}')
        if level >= 7:
            logger.debug(f'(Response) json = {data}')

    try:
        status = r.status_code
        txt = r.text
        if 'json' in r.headers.get('content-type', ''):
            data = r.json()
            if data.get('errors') or data.get('error'):
                logger.error(f'[{RED}error{RESET}] {status} {data}')
            else:
                logger.debug(fmt_status(status))
                stat(r, txt, data)
        else:
            logger.debug(fmt_status(status))
            stat(r, txt, {})
    except Exception as e:
        logger.error(f'Failed to log: {e}')


def fmt_status(status: int) -> str:
    color = None
    if 200 <= status < 300:
        color = GREEN
    elif 300 <= status < 400:
        color = MAGENTA
    elif 400 <= status < 600:
        color = RED
    return f'[{color}{status}{RESET}]'


def save(r: Response, fname: str = f'{time.time_ns()}') -> int:
    if 'json' in r.headers.get('content-type', ''):
        return Path(fname).with_suffix('.json').write_bytes(orjson.dumps(r.json()))
    return Path(fname).with_suffix('.txt').write_text(r.text)
