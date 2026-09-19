"""Supported practice settings and authored conversation starters."""
from fastapi import HTTPException

LANGUAGES = {
    'es': {'name': 'Spanish', 'native': 'Español', 'locale': 'es-ES', 'countries': {'Spain': ['Barcelona', 'Madrid', 'Valencia']},
           'note': 'Barcelona speaks more than one language. Spanish and Catalan are distinct languages.',
           'openings': ['¿Qué te ha tenido más entretenido últimamente: algo que disfrutas o algo de lo que necesitas desconectar?', 'Tenemos que organizar una cena con amigos. ¿Qué plan propondrías y cómo convencerías al resto?', '¿Cómo crees que se puede equilibrar el turismo con las necesidades de quienes viven en la ciudad?', '¿Te ha pasado algo que en su momento te diera rabia y ahora te haga gracia?']},
    'it': {'name': 'Italian', 'native': 'Italiano', 'locale': 'it-IT', 'countries': {'Italy': ['Rome', 'Milan', 'Naples', 'Florence']},
           'note': 'Practice Italian in your chosen city. Regional languages and local varieties are distinct; city selection does not guarantee a local voice.',
           'openings': ['Finalmente abbiamo un momento per chiacchierare. Che cosa ti ha tenuto più occupato ultimamente?', 'Dobbiamo organizzare una cena con gli amici. Che cosa proporresti e come convinceresti gli altri?', 'Secondo te, come si può trovare un equilibrio tra il turismo e le esigenze di chi vive in città?', 'Ti è mai successo qualcosa che sul momento ti ha fatto arrabbiare, ma che ora ti fa ridere?']},
    'ru': {'name': 'Russian', 'native': 'Русский', 'locale': 'ru-RU', 'countries': {'Russia': ['Moscow', 'Saint Petersburg', 'Kazan']},
           'note': 'Practice Russian in your chosen city. A location provides conversational context, not a guarantee of a city-specific accent.',
           'openings': ['Наконец-то у нас есть время спокойно поговорить. Что в последнее время занимало тебя больше всего?', 'Нужно организовать ужин с друзьями. Что бы ты предложил и как убедил бы остальных?', 'Как, по-твоему, найти баланс между развитием туризма и потребностями жителей города?', 'Случалось ли с тобой что-нибудь, что сначала злило, а теперь кажется смешным?']},
    'zh': {'name': 'Mandarin', 'native': '中文（普通话）', 'locale': 'zh-CN', 'countries': {'China': ['Beijing', 'Shanghai', 'Chengdu']},
           'note': 'Practice Mandarin using simplified Chinese. Local languages such as Shanghainese are distinct; choosing a city does not switch the conversation language.',
           'openings': ['终于有时间坐下来聊聊了。最近什么事情让你最忙？是你喜欢的事，还是让你想放松一下的事？', '我们打算和朋友一起吃晚饭。你会提议去哪里，又会怎么说服大家？', '你觉得一座城市应该怎样在发展旅游和照顾本地居民的生活之间找到平衡？', '你有没有遇到过当时很生气，现在想起来却觉得很好笑的事？']},
}
TITLES = ['A café catch-up', 'Dinner with friends', 'Life in the city', 'A story worth telling']
TRANSLATIONS = {
    'es': ['What has been keeping you busy lately: something you enjoy, or something you need a break from?', 'We need to organize dinner with friends. What would you propose and how would you convince everyone else?', 'How do you think tourism can be balanced with the needs of city residents?', 'Has anything happened that annoyed you at the time but now makes you laugh?'],
    'it': ['We finally have a moment to chat. What has been keeping you busiest lately?', 'We need to organize dinner with friends. What would you suggest and how would you persuade the others?', 'How do you think we can balance tourism with the needs of city residents?', 'Has anything ever happened that made you angry at the time but now makes you laugh?'],
    'ru': ['We finally have time to talk calmly. What has occupied you most lately?', 'We need to organize dinner with friends. What would you suggest and how would you persuade the others?', 'How do you think we can balance tourism development with city residents’ needs?', 'Has anything happened that initially annoyed you but now seems funny?'],
    'zh': ['We finally have time to sit down and chat. What has kept you busiest lately? Something you enjoy, or something that makes you want to relax?', 'We plan to have dinner with friends. Where would you suggest going, and how would you persuade everyone?', 'How should a city balance tourism development with looking after local residents’ lives?', 'Have you ever experienced something that made you angry at the time but now seems funny?'],
}
for code, profile in LANGUAGES.items():
    profile['scenes'] = {key: {'title': title, 'opening': opening, 'translation': translation}
        for key, title, opening, translation in zip(('terrace', 'dinner', 'city', 'stories'), TITLES, profile.pop('openings'), TRANSLATIONS[code])}


def location(code, country=None, city=None):
    profile = LANGUAGES.get(code)
    if not profile:
        raise HTTPException(422, 'Choose a supported language.')
    country = country or next(iter(profile['countries']))
    if country not in profile['countries']:
        raise HTTPException(422, 'Choose a country available for this language.')
    city = city or profile['countries'][country][0]
    if city not in profile['countries'][country]:
        raise HTTPException(422, 'Choose a city available for this country.')
    return profile, country, city

LEVEL_GUIDANCE = {
    'beginner': 'Use common everyday words, simple present-tense sentences, and one short concrete question at a time. Reply in 1–2 short sentences. Offer a short model answer when the learner struggles. Explain corrections plainly, without grammar jargon. Prioritize understanding over minor mistakes; avoid unexplained idioms.',
    'intermediate': 'Use everyday vocabulary and a mix of present, past and future forms. Reply in 2–3 sentences with one follow-up question. Encourage reasons and short stories. Explain useful grammar and natural phrasing clearly; explain any idiom you introduce.',
    'advanced': 'Use nuanced conversational language, varied sentence structures and natural register. Reply in 2–5 sentences. Explore opinions, humor and subtext, without forcing slang. Give precise explanations of subtle errors and optional natural alternatives.',
}
LEVEL_STARTERS = {
    'es': {
        'beginner': ['¡Hola! ¿Qué te gusta beber?', '¿Qué te gusta comer?', '¿Te gusta esta ciudad?', '¿Qué haces los fines de semana?'],
        'intermediate': ['¿Qué hiciste el fin de semana? ¿Pudiste descansar?', 'Vamos a cenar con amigos. ¿Qué restaurante elegirías y por qué?', '¿Qué es lo que más te gusta de vivir en una ciudad?', 'Cuéntame algo divertido que te pasó hace poco.'],
    },
    'it': {
        'beginner': ['Ciao! Che cosa ti piace bere?', 'Che cosa ti piace mangiare?', 'Ti piace questa città?', 'Che cosa fai nel fine settimana?'],
        'intermediate': ['Che cosa hai fatto nel fine settimana? Sei riuscito a riposarti?', 'Andiamo a cena con gli amici. Quale ristorante sceglieresti e perché?', 'Che cosa ti piace di più della vita in città?', 'Raccontami qualcosa di divertente che ti è successo di recente.'],
    },
    'ru': {
        'beginner': ['Привет! Что ты любишь пить?', 'Что ты любишь есть?', 'Тебе нравится этот город?', 'Что ты делаешь по выходным?'],
        'intermediate': ['Как прошли твои выходные? Удалось отдохнуть?', 'Мы идём ужинать с друзьями. Какой ресторан ты выберешь и почему?', 'Что тебе больше всего нравится в городской жизни?', 'Расскажи о чём-нибудь смешном, что недавно с тобой случилось.'],
    },
    'zh': {
        'beginner': ['你好！你喜欢喝什么？', '你喜欢吃什么？', '你喜欢这个城市吗？', '你周末做什么？'],
        'intermediate': ['你周末做了什么？休息得怎么样？', '我们要和朋友一起吃晚饭。你会选哪家餐厅？为什么？', '你最喜欢城市生活的哪一点？', '说说最近发生的一件有趣的事吧。'],
    },
}
for code, profile in LANGUAGES.items():
    profile['level_scenes'] = {'advanced': profile['scenes']}
    for level, openings in LEVEL_STARTERS[code].items():
        translations = (['Hello! What do you like to drink?', 'What do you like to eat?', 'Do you like this city?', 'What do you do on weekends?'] if level == 'beginner' else
            ['How was your weekend? Did you get to rest?', 'We are going out to dinner with friends. Which restaurant would you choose, and why?', 'What do you like most about city life?', 'Tell me about something funny or interesting that happened to you recently.'])
        profile['level_scenes'][level] = {key: dict(title=scene['title'], opening=opening, translation=translation)
            for (key, scene), opening, translation in zip(profile['scenes'].items(), openings, translations)}
