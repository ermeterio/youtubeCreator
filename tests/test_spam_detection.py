from pipeline import spam_detection


def test_clean_comment_scores_low():
    score, reasons = spam_detection.spam_score("Vídeo incrível, aprendi muito sobre o Hubble!", "Maria")
    assert score < 20
    assert reasons == []


def test_link_and_keyword_combo_scores_high():
    score, reasons = spam_detection.spam_score(
        "ganhe dinheiro em casa, clique aqui: http://golpe.example.com", "bot123"
    )
    assert score >= 60
    assert any("link" in r for r in reasons)
    assert any("frase suspeita" in r for r in reasons)


def test_excessive_emojis_flagged():
    score, reasons = spam_detection.spam_score("🔥🔥🔥🔥🔥🔥 incrível", "fan")
    assert score >= 15
    assert any("emoji" in r for r in reasons)


def test_confusable_unicode_mix_flagged():
    # "а" aqui é cirílico (U+0430), não latino - mistura clássica de bot.
    score, reasons = spam_detection.spam_score("исsо é golpe", "а")
    assert any("alfabetos" in r for r in reasons)


def test_score_caps_at_100():
    # link (+30) + palavra-chave (+35) + 10 emojis (+15) + mistura latin/cirílico (+25) = 105, deve saturar em 100.
    text = "ganhe dinheiro em http://x.com, confira meu canal 🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥 а"
    score, _ = spam_detection.spam_score(text, "bot")
    assert score == 100


def test_flag_duplicates_same_author_same_text():
    comments = [
        {"id": "1", "author": "bot", "text": "Confira meu canal!"},
        {"id": "2", "author": "bot", "text": "confira meu canal!  "},
        {"id": "3", "author": "outra pessoa", "text": "Confira meu canal!"},
        {"id": "4", "author": "bot", "text": "Mensagem diferente"},
    ]
    duplicates = spam_detection.flag_duplicates(comments)
    assert duplicates == {"1", "2"}


def test_flag_duplicates_empty_author_never_flagged():
    comments = [
        {"id": "1", "author": "", "text": "mesma coisa"},
        {"id": "2", "author": "", "text": "mesma coisa"},
    ]
    assert spam_detection.flag_duplicates(comments) == set()
