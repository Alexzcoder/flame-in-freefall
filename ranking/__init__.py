"""Relevance ranking + auto-generated comparison of PSI combustion investigations.

    from flame.schema import Dataset
    from ranking.rank import rank
    from ranking.compare import compare
    from ranking.scenarios import custom
    ds = Dataset.from_json("dataset/flame_runs.json")
    rank(ds, "moon_base")["results"][:5]
    compare(ds, ["PSI-25", "PSI-99"])
"""
