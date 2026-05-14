# UK National Curriculum statutory word lists
# year_group: 1 = Years 1-2, 3 = Years 3-4, 5 = Years 5-6

# Context sentences for words that have homophones, to disambiguate during audio-only testing.
CONTEXT_SENTENCES = {
    # Year 1–2
    "i":      "I am going to school today.",
    "eye":    "She had a speck of dust in her eye.",
    "our":    "We put our books away before lunch.",
    "hour":   "We waited for one hour.",
    "to":     "She walked to school in the morning.",
    "do":     "What do you want to play?",
    "you":    "Are you coming to the party?",
    "your":   "Is this your pencil?",
    "be":     "Try to be kind to everyone.",
    "we":     "We went to the park after school.",
    "no":     "There is no more cake left.",
    "so":     "It was cold, so we put our coats on.",
    "by":     "The cat sat by the fire.",
    "here":   "Come and sit here next to me.",
    "there":  "The bag is over there by the door.",
    "where":  "Do you know where my bag is?",
    "some":   "Can I have some more juice please?",
    "one":    "I have one sister.",
    "poor":   "The poor dog was lost in the rain.",
    "great":  "You did a great job!",
    "break":  "We had a break at playtime.",
    "steak":  "Grandad likes to eat steak for dinner.",
    "past":   "We walked past the park on the way home.",
    "would":  "I would like some water please.",
    "whole":  "She ate the whole sandwich.",
    # Year 3–4
    "caught":   "She caught the ball with one hand.",
    "eight":    "I have eight crayons in my pencil case.",
    "heard":    "I heard the bell ring at the end of break.",
    "reign":    "During the queen's reign, the country was peaceful.",
    "straight": "Draw a straight line across the page.",
    "through":  "The train went through the tunnel.",
    "weight":   "We measured the weight of the parcel.",
    # Year 5–6
    "muscle": "He strained a muscle in his arm during the race.",
    "symbol": "The heart is a symbol of love.",
}

CURRICULUM = {
    1: [
        "the", "a", "do", "to", "today", "of", "said", "says", "are", "were",
        "was", "is", "his", "has", "I", "you", "your", "they", "be", "he",
        "me", "she", "we", "no", "go", "so", "by", "my", "here", "there",
        "where", "love", "come", "some", "one", "once", "ask", "friend",
        "school", "put", "push", "pull", "full", "house", "our", "door",
        "floor", "poor", "because", "find", "kind", "mind", "behind", "child",
        "children", "wild", "climb", "most", "only", "both", "old", "cold",
        "gold", "hold", "told", "every", "great", "break", "steak", "pretty",
        "beautiful", "after", "fast", "last", "past", "father", "class",
        "grass", "pass", "plant", "path", "bath", "hour", "move", "prove",
        "improve", "sure", "sugar", "eye", "could", "should", "would",
        "who", "whole", "any", "many", "again", "half", "money", "mr",
        "mrs", "people", "looked", "called", "asked", "water", "away",
    ],
    3: [
        "accident", "actually", "address", "answer", "appear", "arrive",
        "believe", "bicycle", "breath", "breathe", "build", "busy", "business",
        "calendar", "caught", "centre", "century", "certain", "circle",
        "complete", "consider", "continue", "decide", "describe", "different",
        "difficult", "disappear", "earth", "eight", "enough", "exercise",
        "experience", "experiment", "extreme", "famous", "favourite", "february",
        "forward", "fruit", "grammar", "group", "guard", "guide", "heard",
        "heart", "height", "history", "imagine", "increase", "important",
        "interest", "island", "knowledge", "learn", "length", "library",
        "material", "medicine", "mention", "minute", "natural", "naughty",
        "notice", "occasion", "often", "opposite", "ordinary", "particular",
        "peculiar", "perhaps", "popular", "position", "possess", "possession",
        "possible", "potatoes", "pressure", "probably", "promise", "purpose",
        "quarter", "question", "recent", "regular", "reign", "remember",
        "sentence", "separate", "special", "straight", "strange", "strength",
        "suppose", "surprise", "therefore", "though", "through", "various",
        "weight", "woman", "women",
    ],
    5: [
        "accommodate", "accompany", "aggressive", "amateur", "ancient",
        "apparent", "appreciate", "attached", "available", "average",
        "awkward", "bargain", "bruise", "category", "cemetery", "committee",
        "communicate", "community", "competition", "conscience", "conscious",
        "controversy", "convenience", "correspond", "criticise", "curiosity",
        "definite", "desperate", "determined", "develop", "dictionary",
        "disastrous", "embarrass", "environment", "equip", "especially",
        "exaggerate", "excellent", "existence", "explanation", "familiar",
        "foreign", "forty", "frequently", "government", "guarantee",
        "harass", "hindrance", "identity", "immediate", "individual",
        "interfere", "interrupt", "language", "leisure", "lightning",
        "marvellous", "mischievous", "muscle", "necessary", "neighbour",
        "nuisance", "occupy", "occur", "opportunity", "parliament",
        "persuade", "physical", "prejudice", "privilege", "profession",
        "programme", "pronunciation", "queue", "recognise", "recommend",
        "relevant", "restaurant", "rhyme", "rhythm", "sacrifice", "secretary",
        "shoulder", "signature", "sincere", "sincerely", "soldier", "stomach",
        "sufficient", "suggest", "symbol", "system", "temperature", "thorough",
        "twelfth", "variety", "vegetable", "vehicle", "yacht",
    ],
}


def seed(db):
    """Idempotently insert curriculum word lists and words."""
    for year_group, words in CURRICULUM.items():
        name = f"Year {year_group}–{year_group + 1}"
        existing = db.execute(
            "SELECT id FROM word_lists WHERE name=? AND year_group=?", (name, year_group)
        ).fetchone()
        if existing:
            list_id = existing["id"]
        else:
            cur = db.execute(
                "INSERT INTO word_lists (name, year_group) VALUES (?,?)", (name, year_group)
            )
            list_id = cur.lastrowid

        for word in words:
            word_lower = word.lower()
            db.execute(
                "INSERT OR IGNORE INTO words (word, list_id) VALUES (?,?)",
                (word_lower, list_id),
            )
            sentence = CONTEXT_SENTENCES.get(word_lower)
            if sentence:
                db.execute(
                    "UPDATE words SET context_sentence=? WHERE word=? AND list_id=?",
                    (sentence, word_lower, list_id),
                )
