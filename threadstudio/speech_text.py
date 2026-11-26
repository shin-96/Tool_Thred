"""Expand Vietnamese chat abbreviations so TTS reads naturally.

Only the SPOKEN text is rewritten; the on-screen card keeps the original.
The dictionary is deliberately conservative: ambiguous codes (hn, bn, đk…)
are left alone rather than guessed wrong. Add entries freely — keys are
matched as whole words, case-insensitively.
"""
import re

ABBR = {
    'ko': 'không', 'kh': 'không', 'hok': 'không', 'hong': 'không', 'hông': 'không',
    'đc': 'được', 'dc': 'được', 'j': 'gì', 's': 'sao', 'r': 'rồi', 'rùi': 'rồi', 'òi': 'rồi',
    'mn': 'mọi người', 'mng': 'mọi người', 'ae': 'anh em', 'ce': 'chị em', 'ac': 'anh chị',
    'ny': 'người yêu', 'gđ': 'gia đình', 'đt': 'điện thoại', 'fb': 'facebook', 'ig': 'instagram',
    'yt': 'youtube', 'ad': 'admin', 'ib': 'nhắn tin', 'inb': 'nhắn tin',
    'trc': 'trước', 'hqua': 'hôm qua', 'hnay': 'hôm nay', 'mik': 'mình', 'mjk': 'mình',
    'vs': 'với', 'v': 'vậy', 'z': 'vậy', 'lun': 'luôn', 'thui': 'thôi', 't': 'tao', 'm': 'mày',
    'cx': 'cũng', 'nx': 'nữa', 'ntn': 'như thế nào', 'tn': 'tin nhắn', 'kb': 'kết bạn',
    'rep': 'trả lời', 'cmt': 'bình luận', 'bl': 'bình luận', 'fl': 'theo dõi',
    'đkí': 'đăng ký', 'dki': 'đăng ký', 'oce': 'ok', 'okie': 'ok', 'oke': 'ok',
}
EMOJI = re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27ff\ufe0f\u200d]')

# Self-censored words the author masked with * or •. Only high-confidence
# entries live here; anything else just loses its mask characters below
# (reading "d" is still better than reading "d sao"). The on-screen card
# always keeps the author's original masked text.
MASKED = {
    'ph*': 'phò',
    'ch*t': 'chết',
    'prost*tution': 'mại dâm',
    's*x': 'sex',
}
_DOTTED = re.compile(r'(?:[A-Za-zÀ-ỹĐđ]\.){2,}[A-Za-zÀ-ỹĐđ]')   # s.e.x -> sex
_MASKED_TOKEN = re.compile(r'[A-Za-zÀ-ỹĐđ][A-Za-zÀ-ỹĐđ*•]*[*•][A-Za-zÀ-ỹĐđ*•]*')


# Strong profanity the voice must never read aloud; the renderer swaps these
# for a censor beep. Accented forms only — unaccented Vietnamese is too
# ambiguous ("cac" is usually just "các"). Phrases come first so the regex
# prefers them over their single-word parts.
PROFANITY = (
    'địt mẹ', 'đụ má', 'vãi lồn', 'vãi cặc', 'con đĩ',
    'địt', 'đụ', 'đéo', 'đĩ', 'đị', 'cặc', 'lồn', 'buồi', 'đcm', 'đmm',
    'fucking', 'fuck', 'shit', 'bitch',
)
_PROFANITY_RE = re.compile(
    r'(?<![A-Za-zÀ-ỹĐđ])(?:' + '|'.join(re.escape(w) for w in PROFANITY) + r')(?![A-Za-zÀ-ỹĐđ])',
    re.IGNORECASE)


def split_profanity(text):
    """Split text into (chunk, is_profanity) pieces covering the whole string."""
    out, pos = [], 0
    for m in _PROFANITY_RE.finditer(text or ''):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text or ''):
        out.append((text[pos:], False))
    return out


def _unmask(text):
    text = _DOTTED.sub(lambda m: m.group(0).replace('.', ''), text)

    def repl(m):
        token = m.group(0)
        return MASKED.get(token.lower(), token.replace('*', '').replace('•', ''))

    return _MASKED_TOKEN.sub(repl, text)


def _number_rules(text):
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*[kK]\b', r'\1 nghìn', text)          # 500k -> 500 nghìn
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*tr(?:iệu)?\b', r'\1 triệu', text)    # 4tr -> 4 triệu
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*củ\b', r'\1 triệu', text)            # 4 củ -> 4 triệu
    text = re.sub(r'(\d)\s*m\b', r'\1 mét', text)                            # 5m -> 5 mét
    text = re.sub(r'(\d)m(\d)', r'\1 mét \2', text)                          # 1m8 -> 1 mét 8
    text = text.replace('%', ' phần trăm')
    return text


def expand_speech(text):
    text = EMOJI.sub('', text or '')
    for junk in ('=))', ':))', ':)', '^^', '~~', '...'):
        text = text.replace(junk, '.' if junk == '...' else ' ')
    text = _number_rules(text)
    text = _unmask(text)

    def repl(m):  # never expand a letter glued to a digit (model names, sizes…)
        if (m.start() and text[m.start() - 1].isdigit()) or (m.end() < len(text) and text[m.end()].isdigit()):
            return m.group(0)
        return ABBR.get(m.group(0).lower(), m.group(0))

    text = re.sub(r'[A-Za-zÀ-ỹĐđ]+', repl, text)
    return re.sub(r'\s+', ' ', text).strip()
