from seed.curriculum_words import seed, CURRICULUM, CONTEXT_SENTENCES


def counts(db):
    return (
        db.execute("SELECT COUNT(*) AS c FROM word_lists").fetchone()["c"],
        db.execute("SELECT COUNT(*) AS c FROM words").fetchone()["c"],
    )


def test_seed_creates_one_list_per_year_group(db):
    seed(db)
    rows = db.execute("SELECT name, year_group FROM word_lists ORDER BY year_group").fetchall()
    assert [r["year_group"] for r in rows] == [1, 3, 5]
    assert rows[0]["name"] == "Year 1–2"


def test_seed_inserts_all_curriculum_words(db):
    seed(db)
    for year_group, words in CURRICULUM.items():
        db_words = {
            r["word"] for r in db.execute(
                """SELECT w.word FROM words w
                   JOIN word_lists wl ON wl.id=w.list_id WHERE wl.year_group=?""",
                (year_group,),
            ).fetchall()
        }
        assert db_words == {w.lower() for w in words}


def test_seed_is_idempotent(db):
    seed(db)
    first = counts(db)
    seed(db)
    assert counts(db) == first


def test_context_sentences_populated_on_words(db):
    seed(db)
    rows = db.execute(
        "SELECT word, context_sentence FROM words WHERE context_sentence IS NOT NULL"
    ).fetchall()
    populated = {r["word"]: r["context_sentence"] for r in rows}
    for word, sentence in CONTEXT_SENTENCES.items():
        assert populated.get(word) == sentence


def test_every_context_sentence_matches_a_curriculum_word():
    curriculum_words = {w.lower() for words in CURRICULUM.values() for w in words}
    orphans = set(CONTEXT_SENTENCES) - curriculum_words
    assert orphans == set(), f"Context sentences for words not in curriculum: {orphans}"


def test_context_sentences_contain_their_word():
    """Each sentence must actually use the word it disambiguates."""
    import re
    for word, sentence in CONTEXT_SENTENCES.items():
        assert re.search(rf"\b{re.escape(word)}\b", sentence.lower()), (
            f"Sentence for {word!r} does not contain the word: {sentence!r}"
        )
