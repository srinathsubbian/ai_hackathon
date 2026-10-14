"""Product catalog loading and keyword search."""
import re

import pandas as pd

REQUIRED_COLUMNS = {
    "product_id", "name", "category", "brand", "price",
    "rating", "stock", "tags", "description",
}
STOPWORDS = {
    "a", "an", "and", "the", "for", "with", "under", "over", "i", "me", "my", "need",
    "want", "looking", "something", "to", "of", "in", "on", "is", "it", "that", "some",
    "good", "best", "please", "can", "you", "find",
}
RESULT_COLUMNS = [
    "product_id", "name", "category", "brand", "price", "rating", "stock", "description",
]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if t not in STOPWORDS}


class Catalog:
    def __init__(self, path: str):
        df = pd.read_csv(path)
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Catalog is missing columns: {sorted(missing)}")
        df["tags"] = df["tags"].fillna("")
        df["description"] = df["description"].fillna("")
        self.df = df

    @property
    def categories(self) -> list[str]:
        return sorted(self.df["category"].unique().tolist())

    def search(self, query: str, category: str | None = None,
               max_price: float | None = None, min_price: float | None = None,
               in_stock_only: bool = True, limit: int = 5) -> list[dict]:
        df = self.df
        if category:
            df = df[df["category"].str.lower() == category.lower()]
        if max_price is not None:
            df = df[df["price"] <= max_price]
        if min_price is not None:
            df = df[df["price"] >= min_price]
        if in_stock_only:
            df = df[df["stock"] > 0]

        q = _tokens(query)
        scores = []
        for _, row in df.iterrows():
            tag_tokens = _tokens(row["tags"].replace(";", " "))
            text_tokens = _tokens(f'{row["name"]} {row["description"]} {row["category"]}')
            matched = q & (tag_tokens | text_tokens)
            # Tag hits count double; rating is a small tiebreaker.
            score = 2 * len(q & tag_tokens) + len(q & text_tokens) + row["rating"] / 10
            scores.append(score if matched else 0.0)

        ranked = df.assign(score=scores)
        ranked = ranked[ranked["score"] > 0].sort_values("score", ascending=False)
        limit = max(1, min(int(limit or 5), 10))
        return ranked.head(limit)[RESULT_COLUMNS].to_dict(orient="records")

    def get(self, product_id: str) -> dict | None:
        match = self.df[self.df["product_id"].str.upper() == product_id.strip().upper()]
        if match.empty:
            return None
        return match.iloc[0].to_dict()
