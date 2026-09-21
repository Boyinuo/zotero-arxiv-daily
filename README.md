<p align="center">
  <a href="" rel="noopener">
 <img width=200px height=200px src="assets/logo.svg" alt="logo"></a>
</p>

<h3 align="center">Zotero-arXiv-Daily</h3>

<div align="center">

  [![Status](https://img.shields.io/badge/status-active-success.svg)]()
  ![Stars](https://img.shields.io/github/stars/TideDra/zotero-arxiv-daily?style=flat)
  [![GitHub Issues](https://img.shields.io/github/issues/TideDra/zotero-arxiv-daily)](https://github.com/TideDra/zotero-arxiv-daily/issues)
  [![GitHub Pull Requests](https://img.shields.io/github/issues-pr/TideDra/zotero-arxiv-daily)](https://github.com/TideDra/zotero-arxiv-daily/pulls)
  [![License](https://img.shields.io/github/license/TideDra/zotero-arxiv-daily)](/LICENSE)
  [<img src="https://api.gitsponsors.com/api/badge/img?id=893025857" height="20">](https://api.gitsponsors.com/api/badge/link?p=PKMtRut1dWWuC1oFdJweyDSvJg454/GkdIx4IinvBblaX2AY4rQ7FYKAK1ZjApoiNhYEeduIEhfeZVIwoIVlvcwdJXVFD2nV2EE5j6lYXaT/RHrcsQbFl3aKe1F3hliP26OMayXOoZVDidl05wj+yg==)

</div>

---

<p align="center"> Recommend new arxiv papers of your interest daily according to your Zotero library.
    <br> 
</p>

> [!IMPORTANT]
> Please keep an eye on this repo, and merge your forked repo in time when there is any update of this upstream, in order to enjoy new features and fix found bugs.

## 🧐 About <a name = "about"></a>

> Track new scientific researches of your interest by just forking (and staring) this repo!😊

*Zotero-arXiv-Daily* finds arxiv papers that may attract you based on the context of your Zotero library, and then sends the result to your mailbox📮. It can be deployed as Github Action Workflow with **zero cost**, **no installation**, and **few configuration** of Github Action environment variables for daily **automatic** delivery.

## ✨ Features
- Totally free! All the calculation can be done in the Github Action runner locally within its quota (for public repo).
- AI-generated TL;DR for you to quickly pick up target papers.
- Affiliations of the paper are resolved and presented.
- Links of PDF and code implementation (if any) presented in the e-mail.
- List of papers sorted by relevance with your recent research interest.
- Fast deployment via fork this repo and set environment variables in the Github Action Page.
- Support LLM API for generating TL;DR of papers.
- Ignore unwanted Zotero papers using a list of glob patterns.
- Support multiple sources of papers to retrieve:
  - arxiv (RSS + API)
  - biorxiv / medrxiv (REST API)
  - IEEE Xplore journals including RA-L, TRO, TASE, TMECH and more (RSS)
  - Nature, Science, IOPscience, and Sage Journals (RSS)
- Cross-run deduplication — papers already sent in previous runs are automatically skipped
- Four reranking strategies: local embedding, API embedding, API rerank, or hybrid scoring

## 📷 Screenshot
![screenshot](./assets/screenshot.png)

## 🚀 Usage
### Quick Start
1. Fork (and star😘) this repo.
![fork](./assets/fork.png)

2. Set Github Action environment variables.
![secrets](./assets/secrets.png)

Below are all the secrets you need to set. They are invisible to anyone including you once they are set, for security.

| Key |Description | Example |
| :---  | :---  | :--- |
| ZOTERO_ID  | User ID of your Zotero account. **User ID is not your username, but a sequence of numbers**Get your ID from [here](https://www.zotero.org/settings/security). You can find it at the position shown in this [screenshot](https://github.com/TideDra/zotero-arxiv-daily/blob/main/assets/userid.png). | 12345678  |
| ZOTERO_KEY | An Zotero API key with read access. Get a key from [here](https://www.zotero.org/settings/security).  | AB5tZ877P2j7Sm2Mragq041H   |
| SENDER | The email account of the SMTP server that sends you email. | abc@qq.com |
| SENDER_PASSWORD | The password of the sender account. Note that it's not necessarily the password for logging in the e-mail client, but the authentication code for SMTP service. Ask your email provider for this.   | abcdefghijklmn |
| RECEIVER | The e-mail address that receives the paper list. | abc@outlook.com |
| OPENAI_API_KEY | API Key when using the API to access LLMs. You can get FREE API for using advanced open source LLMs in [SiliconFlow](https://cloud.siliconflow.cn/i/b3XhBRAm). | sk-xxx |
| OPENAI_API_BASE | API URL when using the API to access LLMs. | https://api.siliconflow.cn/v1 |

Then set an Actions **variable** named `CUSTOM_CONFIG` for your custom configuration.
![vars](./assets/repo_var.png)
![custom_config](./assets/config_var.png)

### Configuration

The application loads [`config/base.yaml`](./config/base.yaml) first, then merges
`CUSTOM_CONFIG` over it through `config/custom.yaml`. You only need to include
values that you want to override. `${oc.env:NAME,default}` reads an environment
variable and uses `default` when that variable is absent.

> [!IMPORTANT]
> A block under `source`, such as `source.sage`, only configures that retriever.
> It does **not** enable it. Every source that should run must also appear in
> `executor.source`. For example, configuring the SAGE feeds requires
> `executor.source: [..., 'sage']`. During a run, look for
> `Retrieving sage papers...` in the Actions log to confirm that it is enabled.

The following multi-source example can be pasted directly into `CUSTOM_CONFIG`.
Remove any source that you do not need from both the `source` configuration and
`executor.source`.
```yaml
zotero:
  user_id: ${oc.env:ZOTERO_ID}
  api_key: ${oc.env:ZOTERO_KEY}
  # Use null for all collections, or YAML lists such as ["Robotics/**"].
  include_path: null
  ignore_path: null

email:
  sender: ${oc.env:SENDER}
  receiver: ${oc.env:RECEIVER}
  smtp_server: smtp.qq.com
  smtp_port: 465
  sender_password: ${oc.env:SENDER_PASSWORD}

llm:
  api:
    key: ${oc.env:OPENAI_API_KEY}
    base_url: ${oc.env:OPENAI_API_BASE}
  generation_kwargs:
    model: gpt-4o-mini
    max_tokens: 16384
  language: English # Output language for title translation and TL;DR.

source:
  arxiv:
    category: ["cs.RO"]
    include_cross_list: false
  ieee:
    feed_urls:
      - "7083369" # RA-L
      - "8860"    # TRO
      - "8856"    # TASE
      - "3516"    # TMECH
  nature:
    feed_urls: ["ncomms"]
  science:
    feed_urls: ["scirobotics", "sciadv"]
  iop:
    feed_urls: ["1748-3190"] # Bioinspiration & Biomimetics
  sage:
    feed_urls:
      - "srb" # Soft Robotics
      - "ijr" # The International Journal of Robotics Research

reranker:
  # Required by api_embedding and hybrid.
  api_embedding:
    key: ${oc.env:OPENAI_API_KEY}
    base_url: ${oc.env:OPENAI_API_BASE}
    model: text-embedding-v4
    batch_size: 10
  # Required by api_rerank and hybrid.
  api_rerank:
    key: ${oc.env:OPENAI_API_KEY}
    base_url: https://dashscope.aliyuncs.com/compatible-api/v1
    model: qwen3-rerank
    instruct: null
    query_max_tokens: 30000

executor:
  debug: ${oc.env:DEBUG,false}
  send_empty: false
  max_paper_num: 15
  # This is the actual enable list. Configured sources omitted here will not run.
  source: ['arxiv', 'ieee', 'nature', 'science', 'iop', 'sage']
  reranker: hybrid # local, api_embedding, api_rerank, or hybrid
  tldr_concurrency: 10
```
Set `source.arxiv.include_cross_list: true` if you want cross-listed papers included.

> [!NOTE]
> `source` and `executor.source` serve different purposes: the first stores
> retriever parameters; the second is the actual enable list. Keep them in sync.

The complete configuration reference is below. `???` marks a required value
that must be supplied by `CUSTOM_CONFIG` or an environment interpolation.
```yaml
zotero:
  user_id: ??? # User ID of your Zotero account.
  api_key: ??? # An Zotero API key with read access.
  include_path: null # A list of glob patterns marking the Zotero collections that should be included. Example: ["2026/survey/**", "2026/reading-group/**"]
  ignore_path: null # A list of glob patterns marking the Zotero collections that should be excluded. Example: ["2026/ignore/**","archive/**"]

source:
  arxiv:
    category: null # The categories of target arxiv papers. Find the abbr of your research area from [here](https://arxiv.org/category_taxonomy). Example: ["cs.AI","cs.CV","cs.LG","cs.CL"]
    include_cross_list: false # Whether to include arXiv cross-list papers in subscribed categories. Example: true
  biorxiv:
    category: null # The categories of target biorxiv papers. Find categories from [here](https://www.biorxiv.org/). Example: ["biochemistry","animal behavior and cognition"]
  medrxiv:
    category: null # The categories of target medrxiv papers. Find categories from [here](https://www.medrxiv.org/) Example: ["psychiatry and clinical psychology", "neurology"]
  ieee:
    feed_urls: null # A list of IEEE Xplore journal RSS feed URLs or publication IDs. Example:
                    #   - "https://ieeexplore.ieee.org/rss/TOC7083369.XML"  # IEEE Robotics and Automation Letters (RA-L)
                    #   - "https://ieeexplore.ieee.org/rss/TOC8860.XML"      # IEEE Transactions on Robotics (TRO)
                    #   - "https://ieeexplore.ieee.org/rss/TOC8856.XML"      # IEEE Trans. on Automation Science and Engineering (TASE)
                    #   - "https://ieeexplore.ieee.org/rss/TOC3516.XML"      # IEEE/ASME Trans. on Mechatronics (TMECH)
                    #   - "7083369"                                           # Shorthand: bare publication ID also works
  nature:
    feed_urls: null # Nature journal slugs or full RSS URLs. Example: ["ncomms"]
  science:
    feed_urls: null # Science journal codes or full RSS URLs. Example: ["scirobotics", "sciadv"]
  iop:
    feed_urls: null # IOPscience ISSNs or full RSS URLs. Example: ["1748-3190"]
  sage:
    feed_urls: # Sage journal codes or full ahead-of-print RSS URLs. Short forms ["srb", "ijr"] also work.
      - "https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=srb&type=axatoc&feed=rss" # Soft Robotics
      - "https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=ijr&type=axatoc&feed=rss" # IJRR

email:
  sender: ??? # The email account of the SMTP server that sends you email. Example: abc@qq.com
  receiver: ??? # The email account that receives the paper list. Example: abc@outlook.com
  smtp_server: ??? # The SMTP server that sends the email. Ask your email provider (Gmail, QQ, Outlook, ...) for its SMTP server. Example: smtp.qq.com
  smtp_port: ??? # The port of SMTP server. Example: 465
  sender_password: ??? # The password of the sender account. Note that it's not necessarily the password for logging in the e-mail client, but the authentication code for SMTP service. Ask your email provider for this. Example: abcdefghijklmn

llm:
  api:
    key: ??? # API Key of your LLM API. Example: sk-xxx
    base_url: ??? # API URL of your LLM API. Example: https://api.openai.com/v1
  generation_kwargs:
  # Arguments for the LLM API. See [here](https://platform.openai.com/docs/api-reference/chat/create) for more details.
    max_tokens: 16384
    model: ???
  language: English # Preferred language for the TL;DR. Example: Chinese

reranker:
  corpus_weighting:
    rating_enabled: true # Read Zotero Style's `rate: 1-5` value from Extra.
    rating_strength: 1.0 # 0 disables rating influence; 1/3/5 stars become 0.5/1/2x.
    unrated_value: 3 # Neutral value for missing or cleared ratings.
  local:
    model: jinaai/jina-embeddings-v5-text-nano-retrieval # The Hugging Face model name of the local embedding model. Example: jinaai/jina-embeddings-v5-text-nano
    encode_kwargs:
    # The kwargs for the encode method of the local embedding model. Details see [here](https://www.sbert.net/docs/package_reference/SentenceTransformer.html#sentence_transformers.SentenceTransformer.encode)
      task: retrieval
      prompt_name: document
  api_embedding:
    key: null # API Key of your embedding model API. Example: sk-xxx
    base_url: null # API URL of your embedding model API. Example: https://dashscope.aliyuncs.com/compatible-mode/v1
    model: null # The model name of the embedding model. Example: text-embedding-v4
    batch_size: null # Max texts per API request. text-embedding-v4: 10. OpenAI: 64.
  api_rerank:
    key: null # API Key for a rerank service. Example: sk-xxx
    base_url: null # Base URL for the rerank API. Example: https://dashscope.aliyuncs.com/compatible-api/v1
    model: null # Rerank model name. Example: qwen3-rerank
    instruct: null # Optional rerank instruction. Example: "Retrieve semantically similar text."
    query_max_tokens: null # Max tokens for the interest query built from Zotero corpus. Default 30000. Adjust based on your library size.
  hybrid: {} # Uses both api_embedding and api_rerank, then averages their raw scores.

executor:
  debug: false # Whether to use debug mode. Example: true
  send_empty: false # Whether to send an empty email even if no new papers today. Example: true
  max_paper_num: 100 # The maximum number of the papers presented in the email. Example: 15
  source: ??? # Enabled retrievers. Example: ['arxiv','biorxiv','medrxiv','ieee','nature','science','iop','sage']
  reranker: local # One of 'local', 'api_embedding', 'api_rerank', or 'hybrid'.
  tldr_concurrency: 10 # Concurrent LLM enrichment requests. Lower this if your provider rate-limits requests.
```

#### Core settings

| Key | Description |
| --- | --- |
| `zotero.user_id` / `zotero.api_key` | Zotero account ID and a read-only API key. Keep the key in Actions Secrets and reference it with `${oc.env:ZOTERO_KEY}`. |
| `zotero.include_path` | Optional **list** of collection-path glob patterns. Only matching Zotero papers form the interest corpus. Use `null` for all collections. |
| `zotero.ignore_path` | Optional list of collection-path glob patterns to exclude. Exclusion takes precedence over inclusion. |
| `email.*` | SMTP sender, receiver, server, port, and sender authorization code/password. Secrets should stay in Actions Secrets. |
| `llm.api` | OpenAI-compatible API key and base URL used for paper enrichment. |
| `llm.generation_kwargs` | Keyword arguments passed to chat completion calls, including the model and optional token limit. |
| `llm.language` | Output language used for title translation and TL;DR generation, e.g. `English` or `Chinese`. |
| `reranker.corpus_weighting` | Controls how Zotero Style `rate: 1-5` metadata is combined with recency when building the interest profile. |

`include_path` and `ignore_path` must be YAML lists or `null`; a single string is
rejected. For example, use `["Robotics/**", "Tactile/**"]`, not
`"Robotics/**"`.

#### Source configuration

| `executor.source` value | Configuration key | Accepted values / examples |
| --- | --- | --- |
| `arxiv` | `source.arxiv.category` | arXiv category list, e.g. `["cs.RO", "cs.AI"]` |
| `biorxiv` | `source.biorxiv.category` | bioRxiv category list |
| `medrxiv` | `source.medrxiv.category` | medRxiv category list |
| `ieee` | `source.ieee.feed_urls` | Publication IDs such as `7083369`, or complete IEEE RSS URLs |
| `nature` | `source.nature.feed_urls` | Journal slugs such as `ncomms`, or complete RSS URLs |
| `science` | `source.science.feed_urls` | Journal codes such as `scirobotics` and `sciadv`, or complete RSS URLs |
| `iop` | `source.iop.feed_urls` | ISSNs such as `1748-3190`, or complete RSS URLs |
| `sage` | `source.sage.feed_urls` | `srb` (Soft Robotics), `ijr` (IJRR), or complete SAGE RSS URLs |

RSS feeds can return an entire current issue or ahead-of-print list.
`data/sent_papers.json` records emailed URLs so that later runs skip them.

#### Reranker configuration

| `executor.reranker` value | Required configuration | Behavior |
| --- | --- | --- |
| `local` | `reranker.local` | Runs a Sentence Transformers embedding model locally; no embedding API is required. |
| `api_embedding` | `reranker.api_embedding` | Calls an OpenAI-compatible embeddings endpoint and ranks by cosine similarity. |
| `api_rerank` | `reranker.api_rerank` | Calls a compatible `/reranks` cross-encoder endpoint, such as Qwen3-Rerank. |
| `hybrid` | Both API blocks above | Averages the raw API embedding and API rerank scores. |

The `llm` settings are separate from the reranker settings. They control title
translation, TL;DR generation, and affiliation extraction after the top
`executor.max_paper_num` candidates have been selected.

#### Executor options

| Key | Default | Description |
| --- | --- | --- |
| `debug` | `false` | Enables debug logs and limits every retriever to a small sample. The Test workflow sets `DEBUG=true`. |
| `send_empty` | `false` | Sends an empty email when no unseen paper remains after deduplication. |
| `max_paper_num` | `100` | Maximum number of top-ranked papers included in an email. |
| `source` | required | Exact list of retrievers to run. Configured sources omitted from this list are ignored. |
| `reranker` | `local` | Selects `local`, `api_embedding`, `api_rerank`, or `hybrid`. |
| `tldr_concurrency` | `10` | Maximum concurrent LLM enrichment requests. |

> [!TIP]
> If a configured source does not appear in the email, inspect the Actions log
> in this order: confirm `Retrieving <source> papers...`, check its retrieved
> count, then check `new papers after deduplication`. A source can run correctly
> but contribute no email item when every URL was already sent or when its
> papers rank below `max_paper_num`.

That's all! Now you can test the workflow by manually triggering it:
![test](./assets/test.png)

> [!NOTE]
> The Test workflow exports `DEBUG=true`. Debug mode enables verbose logging and
> limits each enabled retriever to a small sample (currently up to 10 entries per
> feed). The scheduled workflow uses the configured normal mode. Seeing no email
> item does not necessarily mean retrieval failed: previously sent URLs are
> removed before reranking and email generation.

Then check the log and the receiver email after it finishes.

By default, the main workflow runs on 22:00 UTC everyday. You can change this time by editting the workflow config `.github/workflows/main.yml`.

### Local Running
Supported by [uv](https://github.com/astral-sh/uv), this workflow can easily run on your local device if uv is installed:
```bash
# set all the environment variables
# export ZOTERO_ID=xxxx
# ...
cd zotero-arxiv-daily
uv run main.py
```

## 🚀 Sync with the latest version
This project is in active development. You can subscribe this repo via `Watch` so that you can be notified once we publish new release.

![Watch](./assets/subscribe_release.png)


## 📖 How it works
*Zotero-arXiv-Daily* firstly retrieves all the papers in your Zotero library and all the newly released papers via the configured sources (arXiv RSS/API, bioRxiv/medRxiv REST API, and journal RSS feeds from IEEE Xplore, Nature, Science, IOPscience, and Sage Journals). The re-ranker then scores each candidate paper against your Zotero corpus. Four reranking strategies are available:

- **local**: Downloads a sentence-transformers model and computes cosine similarity locally (bi-encoder).
- **api_embedding**: Calls an embedding API (e.g. text-embedding-v4) to encode abstracts into vectors, then computes cosine similarity (bi-encoder).
- **api_rerank**: Calls a cross-encoder rerank API (e.g. Qwen3-Rerank). The Zotero corpus is fused into an interest query, and the model jointly scores each candidate document against it — offering higher semantic precision.
- **hybrid**: Runs both `api_embedding` and `api_rerank`, then averages their raw scores.

If a Zotero item has a Zotero Style rating stored as `rate: 1` through
`rate: 5` in its Extra field, the rating is combined with the existing
recency weight when building the interest profile. Unrated items remain
neutral. Configure this under `reranker.corpus_weighting`; setting
`rating_strength: 0` restores recency-only weighting.

The TLDR of each paper is generated by LLM, given the text extracted from the paper (TeX source/HTML/PDF for arXiv, abstract-only for bioRxiv/medRxiv and journal RSS sources). When a journal RSS entry has a DOI but no usable abstract, the pipeline tries Crossref first and OpenAlex second before reranking and TLDR generation. Papers that were already sent in previous runs are tracked in `data/sent_papers.json` and automatically skipped.

## 📌 Limitations
- The recommendation algorithm is very simple, it may not accurately reflect your interest. Welcome better ideas for improving the algorithm!
- High `MAX_PAPER_NUM` can lead the execution time exceed the limitation of Github Action runner (6h per execution for public repo, and 2000 mins per month for private repo). Commonly, the quota given to public repo is definitely enough for individual use. If you have special requirements, you can deploy the workflow in your own server, or use a self-hosted Github Action runner, or pay for the exceeded execution time.


## 📃 License
Distributed under the AGPLv3 License. See `LICENSE` for detail.

## ❤️ Acknowledgement
- [pyzotero](https://github.com/urschrei/pyzotero)
- [arxiv](https://github.com/lukasschwab/arxiv.py)
- [sentence_transformers](https://github.com/UKPLab/sentence-transformers)

## ☕ Buy Me A Coffee
If you find this project helpful, welcome to sponsor me via WeChat or via [ko-fi](https://ko-fi.com/tidedra).
![wechat_qr](assets/wechat_sponsor.JPG)


## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=TideDra/zotero-arxiv-daily&type=Date)](https://star-history.com/#TideDra/zotero-arxiv-daily&Date)
