"""Word-edit similarity of ASR text, not acoustic pronunciation assessment."""
import re
import unicodedata


def tokens(text):
    # ASR often omits ё dots and printed stress marks. Ignore these and punctuation.
    text = unicodedata.normalize('NFD', text.lower().replace('ё', 'е'))
    text = unicodedata.normalize('NFC', ''.join(c for c in text if c not in ('\u0301', '\u0300')))
    return re.findall(r'[^\W_]+', text, flags=re.UNICODE)


def compare(target, transcript):
    expected, heard = tokens(target), tokens(transcript)
    rows, cols = len(expected), len(heard)
    dp = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows + 1): dp[i][0] = i
    for j in range(cols + 1): dp[0][j] = j
    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + (expected[i-1] != heard[j-1]))
    differences = []
    i, j = rows, cols
    while i or j:
        if i and j and dp[i][j] == dp[i-1][j-1] + (expected[i-1] != heard[j-1]):
            if expected[i-1] != heard[j-1]:
                differences.append({'kind':'different', 'expected':expected[i-1], 'heard':heard[j-1]})
            i -= 1; j -= 1
        elif i and dp[i][j] == dp[i-1][j] + 1:
            differences.append({'kind':'missing', 'expected':expected[i-1], 'heard':''}); i -= 1
        else:
            differences.append({'kind':'added', 'expected':'', 'heard':heard[j-1]}); j -= 1
    return {'mode':'phrase_match', 'match_score':round(100 * max(0, 1 - dp[rows][cols] / max(rows, 1)), 1),
            'transcript':transcript, 'target':target, 'differences':list(reversed(differences))}
