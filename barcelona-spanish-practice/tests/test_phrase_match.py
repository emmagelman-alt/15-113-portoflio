import pytest
from phrase_match import compare

@pytest.mark.parametrize('target,heard,score', [
    ('Привет, Алёна!', 'привет алена',100),
    ('Я люблю читать книги', 'Я люблю книги',75),
    ('Я люблю читать книги', 'Я люблю писать книги',75),
    ('Я люблю читать книги', 'Я очень люблю читать книги',75),
    ('Да', 'совсем другие слова',0),
])
def test_scores(target, heard, score):
    assert compare(target,heard)['match_score'] == score

def test_differences():
    assert compare('я люблю чай', 'я люблю кофе')['differences'] == [{'kind':'different','expected':'чай','heard':'кофе'}]
