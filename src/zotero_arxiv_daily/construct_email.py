from .protocol import Paper
import math


framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""

def get_empty_html():
  block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        No Papers Today. Take a Rest!
    </td>
  </tr>
  </table>
  """
  return block_template

JOURNAL_COLORS: dict[str, str] = {
    "RA-L":  "#d41515",   # red
    "TRO":   "#c75b1a",   # orange
    "TASE":  "#2e7d32",   # green
    "TMECH": "#6a1b9a",   # purple
    "RAM":   "#c2185b",   # pink
    "THMS":  "#0277bd",   # light blue
    "TCYB":  "#00838f",   # teal
    "TSMC":  "#5d4037",   # brown
    "TIE":   "#4527a0",   # deep purple
    "TMM":   "#ef6c00",   # amber
    "JBHI":  "#1b5e20",   # dark green
    "IEEE":  "#37474f",   # blue-grey (fallback)
    "arXiv": "#b31b1b",   # arXiv red
    "arxiv": "#b31b1b",   # arXiv red (lowercase fallback)
    "biorxiv":  "#997a00",  # gold-brown
    "medrxiv":  "#990000",  # dark red
}

def _source_color(source: str) -> str:
    return JOURNAL_COLORS.get(source, JOURNAL_COLORS.get(source.upper(), "#555"))


def get_block_html(title:str, authors:str, rate:str, tldr:str, pdf_url:str, affiliations:str=None, pub_date:str=None, journal:str=None, title_cn:str=None):
    if pub_date:
        if journal:
            color = _source_color(journal)
            date_html = (
                f'<strong>Published:</strong> {pub_date} &nbsp; | &nbsp; '
                f'<span style="color:{color};font-weight:bold;">{journal}</span>'
            )
        else:
            date_html = f'<strong>Published:</strong> {pub_date}'
    else:
        date_html = ''
    title_cn_html = f'<br><span style="font-size:16px;color:#555;">{title_cn}</span>' if title_cn else ''
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {title}{title_cn_html}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 8px 0;">
            {authors}
            <br>
            <i>{affiliations}</i>
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 4px 0;">
            {pub_date_html}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Relevance:</strong> {rate}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>TLDR:</strong> {tldr}
        </td>
    </tr>

    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">PDF</a>
        </td>
    </tr>
</table>
"""
    return block_template.format(title=title, authors=authors, rate=rate, tldr=tldr, pdf_url=pdf_url, affiliations=affiliations, pub_date_html=date_html, title_cn_html=title_cn_html)

def get_stars(score:float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 3
    high = 8
    if score <= low:
        return f'<span style="color:#999;">{score:.1f} (no match)</span>'
    elif score >= high:
        return ('<div class="star-wrapper">' + full_star * 5
                + f'</div> <span style="color:#333;">{score:.1f}</span>')
    else:
        interval = (high - low) / 10  # 10 half-star steps across the range
        star_num = math.ceil((score - low) / interval)
        full_star_num = star_num // 2
        half_star_num = star_num % 2
        return ('<div class="star-wrapper">'
                + full_star * full_star_num
                + half_star * half_star_num
                + f'</div> <span style="color:#333;">{score:.1f}</span>')


def render_email(papers:list[Paper]) -> str:
    parts = []
    if len(papers) == 0 :
        return framework.replace('__CONTENT__', get_empty_html())
    
    for p in papers:
        rate = get_stars(p.score) if p.score is not None else ''
        #rate = round(p.score, 1) if p.score is not None else 'Unknown'
        author_list = [a for a in p.authors]
        num_authors = len(author_list)
        if num_authors <= 5:
            authors = ', '.join(author_list)
        else:
            authors = ', '.join(author_list[:3] + ['...'] + author_list[-2:])
        if p.affiliations is not None:
            affiliations = p.affiliations[:5]
            affiliations = ', '.join(affiliations)
            if len(p.affiliations) > 5:
                affiliations += ', ...'
        else:
            affiliations = 'Unknown Affiliation'
        link_url = p.pdf_url or p.url
        parts.append(get_block_html(p.title, authors, rate, p.tldr, link_url, affiliations, p.pub_date, p.journal, p.title_cn))

    content = '<br>' + '</br><br>'.join(parts) + '</br>'
    return framework.replace('__CONTENT__', content)
