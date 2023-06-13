import asyncio
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import aiofiles
import orjson
from httpx import URL, AsyncClient, Client
from selectolax.lexbor import LexborHTMLParser
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

base = "https://www.redditstatic.com/desktop2x"


def get_js_mappings() -> set:
    client = init_client()
    r = client.get(f"{base}/runtime~Reddit.bd4ca1f008dbfcfcf4f4.js")  # todo: dynamic
    op_key_map = re.search(
        '\[\w\]\|\|\w\)\+"\."\+([^\[]*)\[\w\]\+"\.js"', r.text
    ).group(1)
    data = []
    for key in op_key_map.split(","):
        temp = re.sub("[}{]", "", key)
        x = re.findall('([\=\+\.\/_\-\w~]+"?:)', temp)[0]
        y = re.sub(f"^{x}", f'"{x[:-1]}":', temp)
        data.append(y)
    runtime_map = orjson.loads(f"{{{','.join(data)}}}")
    write_json("runtime_map.json", runtime_map)
    return {f"{base}/{k}.{v}.js" for k, v in runtime_map.items()}


def get_js():
    async def get(c: AsyncClient, url: str) -> None:
        try:
            fname = out / URL(url).path.split("/")[-1]
            r = await c.get(url)
            async with aiofiles.open(fname, "wb") as fp:
                await fp.write(r.content)
        except Exception as e:
            print(f"failed\n{e}")

    async def process():
        client = init_client()
        r = client.get("https://www.reddit.com/")
        html = LexborHTMLParser(r.text)
        urls = {
            x.attrs.get("key")
            for s in html.css("link")
            if (x := s).attrs.get("as") == "script"
        }
        urls |= get_js_mappings()
        client = init_client()
        async with AsyncClient(headers=client.headers, cookies=client.cookies) as c:
            return await tqdm_asyncio.gather(
                *(get(c, url) for url in urls), desc="downloading js files"
            )

    out = Path("js")
    out.mkdir(exist_ok=True, parents=True)
    asyncio.run(process())


def get_operations():
    operations = {}
    for p in tqdm(list(Path("js").iterdir()), desc="Getting GraphQL operations"):
        try:
            expr = "\"\.\/src\/redditGQL\/operations\/(\w+)\.json\":function\(\w\)\{\w\.exports=JSON\.parse\('(.*)'\)}"
            operations |= {
                x: orjson.loads(y)
                for x, y in filter(
                    len,
                    (y for x in p.read_text().split(",") for y in re.findall(expr, x)),
                )
            }
        except Exception as e:
            print(e)
    write_json("operations.json", operations)
    return operations


def fmt_js(max_workers=16):
    """
    Do not run before get_operations(). the regex relies on un-formatted code.
    """
    n = max_workers
    files = list(Path("js").iterdir())
    batches = [files[i: i + n] for i in range(0, len(files), n)]
    print(f"batches: {len(batches)}")
    with ThreadPoolExecutor(max_workers=n) as executor:
        for batch in batches:
            executor.submit(subprocess.run, ["npx", "prettier", "--write"] + batch)


def init_client():
    headers = {
        "authority": "gql.reddit.com",  # ,"www.reddit.com",
        "authorization": "",  # todo: generate token
        "accept-language": "en-GB,en;q=0.9",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    }
    client = Client(headers=headers, follow_redirects=True)
    client.get("https://www.reddit.com/")  # generate cookies
    client.headers.update(
        {
            "x-reddit-compression": "1",
            "x-reddit-loid": client.cookies.get("loid", ""),
            "x-reddit-session": client.cookies.get("session", ""),
        }
    )
    return client


def write_json(fname: str, data: dict | list):
    Path(fname).write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


def main() -> int:
    get_js()
    get_operations()
    # fmt_js()
    return 0


if __name__ == "__main__":
    exit(main())
