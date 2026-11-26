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
    'bt': 'bình thường', 'klq': 'không liên quan', 'uk': 'ừ', 'uh': 'ừ',
    'hem': 'không', 'khum': 'không', 'khg': 'không', 'chx': 'chưa',
    'ròi': 'rồi', 'zậy': 'vậy', 'lm': 'làm', 'nt': 'nhắn tin', 'tym': 'tim',
    'avt': 'avatar', 'vd': 'ví dụ', 'vde': 'vấn đề', 'acc': 'tài khoản',
    'gv': 'giáo viên', 'sđt': 'số điện thoại', 'ex': 'người yêu cũ',
    'iu': 'yêu', 'xink': 'xinh', 'dth': 'dễ thương', 'tks': 'cảm ơn',
    'sr': 'xin lỗi', 'mxh': 'mạng xã hội', 'cđm': 'cộng đồng mạng',
    'hcm': 'Hồ Chí Minh', 'sg': 'Sài Gòn', 'k': 'không', 'e': 'em',
    'bít': 'biết', 'vch': 'vãi chưởng', 'vk': 'vợ', 'ox': 'ông xã',
    'ms': 'mới', 'kkk': 'ha ha',
    'a': 'anh', 'b': 'bạn', 'bn': 'bạn', 'ng': 'người', 'ngta': 'người ta',
    'str': 'story', 'tk': 'tài khoản', 'zl': 'zalo', 'ytb': 'youtube',
    'gg': 'google', 'sp': 'sản phẩm', 'cfs': 'confession', 'rv': 'review',
    'nyc': 'người yêu cũ', 'hs': 'học sinh', 'sv': 'sinh viên',
    'ph': 'phụ huynh', 'đh': 'đại học', 'gi': 'gì', 'thoy': 'thôi',
    'hoy': 'thôi', 'nhen': 'nhé', 'uhm': 'ừ', 'cũg': 'cũng',
    'hmai': 'ngày mai', 'ngmai': 'ngày mai', 'zui': 'vui', 'juan': 'chuẩn',
    'sịn': 'xịn', 'phake': 'hàng giả', 'auth': 'hàng chính hãng',
    # Profanity INITIALISMS are not beeped: Vietnamese readers say the letter
    # names out loud, so the voice does the same (dcm -> "đờ cờ mờ").
    'dcm': 'đờ cờ mờ', 'đcm': 'đờ cờ mờ', 'cl': 'cờ lờ',
    'đm': 'đờ mờ', 'đmm': 'đờ mờ mờ',
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
    'địt mẹ', 'đụ má', 'vãi lồn', 'vãi cặc', 'con đĩ', 'đù má',
    'địt', 'đụ', 'đéo', 'đĩ', 'đị', 'cặc', 'lồn', 'buồi',
    'fucking', 'fuck', 'fuk', 'fck', 'shit', 'bitch',
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


_CAP = {'1': 'một', '2': 'hai', '3': 'ba'}


def _number_rules(text):
    text = re.sub(r'\bin4\b', 'thông tin', text, flags=re.IGNORECASE)        # xin in4 -> xin thông tin
    text = re.sub(r'\bc([123])\b', lambda m: 'cấp ' + _CAP[m.group(1)], text, flags=re.IGNORECASE)  # hs c3 -> cấp ba
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*[kK]\b', r'\1 nghìn', text)          # 500k -> 500 nghìn
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*tr(?:iệu)?\b', r'\1 triệu', text)    # 4tr -> 4 triệu
    text = re.sub(r'(\d+(?:[.,]\d+)?)\s*củ\b', r'\1 triệu', text)            # 4 củ -> 4 triệu
    text = re.sub(r'(\d)\s*m\b', r'\1 mét', text)                            # 5m -> 5 mét
    text = re.sub(r'(\d)m(\d)', r'\1 mét \2', text)                          # 1m8 -> 1 mét 8
    text = text.replace('%', ' phần trăm')
    return text


_BT_KNOW_PREV = {'có', 'ai', 'sao', 'chả', 'chẳng', 'đâu', 'làm'}
_BT_KNOW_NEXT = {'không', 'chưa', 'gì', 'đâu', 'ai', 'là', 'nói', 'làm', 'được', 'thế', 'bao', 'mấy'}


def _neighbor(text, m, after):
    part = text[m.end():] if after else text[:m.start()]
    words = re.findall(r'[A-Za-zÀ-ỹĐđ]+', part)
    if not words:
        return ''
    return (words[0] if after else words[-1]).lower()


def expand_speech(text):
    text = EMOJI.sub('', text or '')
    for junk in ('=))', ':))', ':)', ':v', '^^', '~~', '...'):
        text = text.replace(junk, '.' if junk == '...' else ' ')
    text = text.replace('kkkk', 'ha ha').replace('kkk', 'ha ha')
    # Elongated spellings (lunnn, ơiii, đẹppp): collapse 3+ repeated letters so
    # the dictionary below sees the base word.
    text = re.sub(r'([A-Za-zÀ-ỹĐđ])\1{2,}', r'\1', text)
    text = _number_rules(text)
    text = _unmask(text)

    def repl(m):  # never expand a letter glued to a digit (model names, sizes…)
        if (m.start() and text[m.start() - 1].isdigit()) or (m.end() < len(text) and text[m.end()].isdigit()):
            return m.group(0)
        low = m.group(0).lower()
        if low == 'bt':  # bt = biết or bình thường, decided by the neighbouring word
            if _neighbor(text, m, False) in _BT_KNOW_PREV or _neighbor(text, m, True) in _BT_KNOW_NEXT:
                return 'biết'
            return 'bình thường'
        return ABBR.get(low, m.group(0))

    text = re.sub(r'[A-Za-zÀ-ỹĐđ]+', repl, text)
    return re.sub(r'\s+', ' ', text).strip()
