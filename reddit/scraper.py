import asyncio
import logging.config
import platform
from urllib.parse import urlencode

import websockets
from httpx import Client, Limits, AsyncClient
from selectolax.lexbor import LexborHTMLParser
from tqdm.asyncio import tqdm_asyncio

from .constants import *
from .util import *

try:
    if get_ipython().__class__.__name__ == 'ZMQInteractiveShell':
        import nest_asyncio

        nest_asyncio.apply()
except:
    ...

if platform.system() != 'Windows':
    try:
        import uvloop

        uvloop.install()
    except ImportError as e:
        ...


class Scraper:
    def __init__(self, username: str = None, password: str = None, session: Client = None, **kwargs):
        self.guest = False
        self.logger = self._init_logger(kwargs.get('log_config', False))
        self.session = self._init_session(username, password, session, **kwargs)
        self.debug = kwargs.get('debug', 0)
        self.out_path = Path('data')
        self.gql = 'https://gql.reddit.com'
        self.api = 'https://www.reddit.com/api'

    def _init_session(self, *args, **kwargs) -> Client:
        """
        Initialize a guest or authenticated session.

        @param args: optional arguments: username, password, session
        @param kwargs: optional keyword arguments
        """
        username, password, session = args
        if session and all(session.cookies.get(c) for c in {'USER', 'csrf_token'}):
            # authenticated session provided
            return session
        if not session:
            # no session provided, log-in to authenticate
            return self.login(username, password)

        self.guest = True
        # create guest session
        client = Client(
            follow_redirects=True,
            headers={
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'
            },
        )
        # generate bearer token
        r = client.get('https://www.reddit.com')
        data = extract_json(LexborHTMLParser(r.text).css_first('script#data').text())
        bearer_token = data['user']['session']['accessToken']
        # generate csrf token
        r = client.get('https://www.reddit.com/account/sso/one_tap/')
        csrf = (LexborHTMLParser(r.text).css_first('input[name=csrf_token]').attributes['value'])
        client.cookies.set('csrf_token', csrf)
        client.headers.update({
            'authority': 'gql.reddit.com',
            'authorization': f'Bearer {bearer_token}',
            'accept-language': 'en-GB,en;q=0.9',
            'x-reddit-compression': '1',
            'x-reddit-loid': client.cookies.get('loid', ''),
            'x-reddit-session': client.cookies.get('session', ''),
        })
        return client

    def login(self, username: str, password: str) -> Client:
        """
        Log-in to Reddit and return authenticated session.

        @param username: Reddit username
        @param password: Reddit password
        @return: authenticated session object
        """
        client = Client(
            follow_redirects=True,
            headers={
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'
            },
        )
        # generate csrf token
        r = client.get('https://www.reddit.com/account/sso/one_tap/')
        csrf = (LexborHTMLParser(r.text).css_first('input[name=csrf_token]').attributes['value'])
        # important: issues with cookies.update(), have to do this crap
        client.cookies.delete('USER')
        client.cookies.delete('csrf_token')
        client.cookies.set('csrf_token', csrf)
        client.cookies = dict(client.cookies) | {'csrf_token': csrf, 'USER': ''}
        data = {
            'csrf_token': csrf,
            'otp': '',
            'password': password,
            'dest': 'https://www.reddit.com',
            'username': username,
        }
        client.post('https://www.reddit.com/login', data=urlencode(data))
        r = client.get('https://www.reddit.com')
        data = extract_json(LexborHTMLParser(r.text).css_first('script#data').text())
        token = data['user']['session']['accessToken']
        # important: issues with headers.update(), have to do this crap
        client.cookies.delete('loid')
        client.cookies.delete('session')
        client.headers = dict(client.headers) | {
            'authorization': f'Bearer {token}',
            'x-reddit-compression': '1',
            'x-reddit-loid': client.cookies.get('loid', ''),
            'x-reddit-session': client.cookies.get('session', ''),
        }
        return client

    def comment(self, post_id: str, text: str):
        """
        Comment on a post.

        @param post_id: the post id.
        @param text: the comment text.
        @return: json response indicating success or failure metadata.
        """
        params = {
            "rtj": "only",
            "emotes_as_images": "true",
            "redditWebClient": "desktop2x",
            "app": "desktop2x-client-production",
            "raw_json": "1",
            "gilding_detail": "1",
        }
        data = {
            "api_type": "json",
            "return_rtjson": "true",
            "thing_id": f"t3_{post_id}",
            "richtext_json": '{"document":[{"e":"par","c":[{"e":"text","t":"' + text + '"}]}]}',
        }
        r = self.session.post("https://oauth.reddit.com/api/comment.json", params=params, data=urlencode(data))
        if self.debug: log(self.logger, self.debug, r)
        return r.json()

    def search(self, query: str, **kwargs) -> dict:
        """
        Search for posts, communities, authors, and comments.

        @param query: the search term.
        @param kwargs: optional search parameters, see below:
        {
            'includePosts': False
            'includeCommunities': False
            'includeAuthors': False
            'includeComments': False
            'communitySearch': False,
            'customFeedSearch': False,
            'postsAfter': None,
            'communitiesAfter': None,
            'authorsAfter': None,
            'commentsAfter': None,
        }
        @return: a dict containing the search results.
        """
        filters = [{'key': k, 'value': v} for k, v in kwargs.pop('filters', {}).items()]
        json = {
            'id': Operation.GeneralSearch,
            'variables': {
                'query': query,
                'filters': filters,
                'productSurface': 'web2x',
                **kwargs,
            },
        }
        r = self.session.post(self.gql, json=json)
        if self.debug: log(self.logger, self.debug, r)
        return r.json()

    def popular(self, region: str = Location.All, sort: str = Sort.Hot, range: str = Range.All, **kwargs) -> dict:
        """
        Get popular posts

        @param region: location to get popular posts from. See `Location` for options.
        @param sort: sort type. See `Sort` for options.
        @param range: time range. See `Range` for options.
        @param kwargs: optional keyword arguments, see below:
        {
            'region': 'GLOBAL',
            'sort': 'HOT',
            'range': 'ALL',
            'includeAchievementFlairs': False,
            'includeAppliedFlair': False,
            'includeCustomEmojis': False,
            'includeDevPlatformMetadata': True,
            'includeIdentity': False,
            'includeQuestions': False,
            'includeRecents': False,
            'includeRedditorKarma': False,
            'includeRules': False,
            'includeSubredditChannels': True,
            'includeSubredditLinks': False,
            'includeSubredditRankings': True,
            'includeTopicLinks': False,
            'includeTrending': True,
            'isAdHocMulti': False,
            'isAll': False,
            'isFake': True,
            'isLoggedOutGatedOptedin': False,
            'isLoggedOutQuarantineOptedin': False,
            'isPopular': True,
        }
        @return: a dict containing the popular posts
        """
        _kwargs = {'sort': sort,
                   'range': range,
                   'region': region} | kwargs
        json = {
            'id': Operation.PopularFeedElements,
            'variables': {
                'recentPostIds': [],
                'subredditNames': [],
                **_kwargs,
            },
        }
        r = self.session.post(self.gql, json=json)
        if self.debug: log(self.logger, self.debug, r)
        return r.json()

    def front_page(self, sort: str = Sort.New, **kwargs) -> dict:
        """
        Get Reddit's front page
        
        @param sort: sort type. See `Sort` for options.
        @param kwargs: optional keyword arguments, see below:
        {       
            'includeCommunityDUs': True,
            'includeInterestTopics': True,
            'includeFeaturedAnnouncements': True,
            'includeLiveEvents': True,
            'includeIdentity': True,
            'includePostRecommendations': True
        }
        @return: a dict containing the front page data.
        """
        _kwargs = {'includeCommunityDUs': True,
                   'includeInterestTopics': True,
                   'includeFeaturedAnnouncements': True,
                   'includeLiveEvents': True,
                   'includeIdentity': True,
                   'includePostRecommendations': True} | kwargs
        payload = {
            'id': Operation.Frontpage,
            'variables': {
                'sort': sort,
                **_kwargs,
                'recentPostIds': [],
            },
        }
        r = self.session.post(self.gql, json=payload)
        if self.debug: log(self.logger, self.debug, r)
        return r.json()

    def trending_searches(self) -> dict:
        """
        Get trending searches

        @return: dict containing the trending searches.
        """
        params = {
            "withAds": "1",
            "subplacement": "tile",
            "raw_json": "1",
            "gilding_detail": "1",
        }
        r = self.session.get(f"{self.api}/trending_searches_v1.json", params=params)
        return r.json()

    def subreddit(self, name: str) -> dict:
        """
        Get subreddit data

        @param name: name of the subreddit.
        @return: dict containing the subreddit data.
        """
        json = {
            "id": Operation.SubredditPageExtra,
            "variables": {"subredditName": name},
        }
        # headers = dict(self.session.headers) | {"content-type": "application/json"}
        r = self.session.post(self.gql, json=json)
        if self.debug: log(self.logger, self.debug, r)
        return r.json()

    def homepage(self) -> dict:
        """
        Get the homepage data

        @return: dict containing the homepage data.
        """
        r = self.session.get("https://www.reddit.com/")
        if self.debug: log(self.logger, self.debug, r)
        script = LexborHTMLParser(r.text).css_first("script#data")
        return extract_json(script.text())

    def posts(self, mapping: dict) -> list[dict]:
        """
        Get posts from subreddits

        @param mapping: a dict representing a mapping of subreddit names to post ids.
        @return: a list of dicts containing the post data.
        """

        async def get(session: AsyncClient, post_id: str, url: str):
            r = await session.get(url)
            script = LexborHTMLParser(r.text).css_first("script#data")
            return {post_id: extract_json(script.text())}

        async def process():
            urls = []
            for k, v in mapping.items():
                if isinstance(v, list):
                    urls.extend((vv, f'https://www.reddit.com/r/{k}/comments/{vv}') for vv in v)
                else:
                    urls.append((v, f'https://www.reddit.com/r/{k}/comments/{v}'))

            limits = Limits(max_connections=100)
            headers, cookies = self.session.headers, self.session.cookies
            async with AsyncClient(limits=limits, headers=headers, cookies=cookies, timeout=20,
                                   follow_redirects=True) as c:
                return await tqdm_asyncio.gather(*(get(c, _id, url) for _id, url in urls), desc="Getting posts")

        return asyncio.run(process())

    def live_comments(self, mapping: dict):
        """
        Log live comments from subreddits

        @param mapping: a dict representing a mapping of subreddit names to post ids.
        @return None
        """

        async def listener(uri: str):
            async with websockets.connect(uri) as ws:
                while True:
                    msg = await ws.recv()
                    try:
                        data = orjson.loads(msg)
                        payload = data.get("payload", {})
                        author_id = payload.get("author_id")
                        # subreddit = payload.get("subreddit")
                        author = payload.get("author")
                        context = payload.get("context")
                        full_date = payload.get("full_date")
                        body = payload.get("body") or " ".join(find_key(payload, "t"))
                        link = f"https://reddit.com{context}"

                        print(f"{full_date}\n{GREEN}{author}{RESET}({author_id})\n{body}\n{link}\n")

                    except Exception as e:
                        print(e)

        async def process(posts: list[dict]):
            ws_uris = []
            for post in posts:
                k, v = tuple(post.items())[0]
                if uri := v['posts']['models'].get(f't3_{k}', {}).get('liveCommentsWebsocket'):
                    ws_uris.append(uri)
            await asyncio.gather(*(listener(uri) for uri in ws_uris))

        posts = self.posts(mapping)
        return asyncio.run(process(posts))

    @staticmethod
    def _init_logger(cfg: dict) -> Logger:
        if cfg:
            logging.config.dictConfig(cfg)
        else:
            logging.config.dictConfig(LOG_CONFIG)

        # only support one logger
        logger_name = list(LOG_CONFIG['loggers'].keys())[0]

        # set level of all other loggers to ERROR
        for name in logging.root.manager.loggerDict:
            if name != logger_name:
                logging.getLogger(name).setLevel(logging.ERROR)

        return logging.getLogger(logger_name)
