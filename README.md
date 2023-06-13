
### Installation
```
pip install reddit-api-client
```

### Examples

#### Guest Endpoints
```python
from reddit.scraper import Scraper

reddit = Scraper()

homepage = reddit.homepage()

popular = reddit.popular()

front_page = reddit.front_page()

subreddit = reddit.subreddit("pics")

search = reddit.search(
    'api blackout',
    includePosts=True,
    includeCommunities=True,
    includeAuthors=True,
    includeComments=True,
    # communitySearch=False,
    # customFeedSearch=False,
    # postsAfter=None,
    # communitiesAfter=None,
    # authorsAfter=None,
    # commentsAfter=None,
    filters={
        'nsfw': '0',  # {'1', '0'},
        'time_range': 'null',  # {'hour', 'day', 'week', 'month', 'year', 'null'},
        'post_types': 'null',  # {'gif', 'image', 'link', 'poll', 'text', 'video', 'null'},
        'result_types': '',  # {'subreddit', 'profile', ''}
    },
    sort='NEW',  # {'RELEVANCE', 'HOT', 'TOP', 'NEW', 'COMMENTS'}
)
```

#### Auth Endpoints
```python
from reddit.scraper import Scraper

username, password = ..., ...
reddit = Scraper(username, password)

# get data from posts
posts = reddit.posts({
    'pics': ['147p5ql', '146zsax'],
    'funny': '143wysp',
})

# comment on a post
reddit.comment('146zsax', 'test 123')
```