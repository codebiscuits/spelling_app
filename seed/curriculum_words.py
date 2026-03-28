# UK National Curriculum statutory word lists
# year_group: 1 = Years 1-2, 3 = Years 3-4, 5 = Years 5-6

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
            db.execute(
                "INSERT OR IGNORE INTO words (word, list_id) VALUES (?,?)",
                (word.lower(), list_id),
            )
