"""A stand-in for the code the synthetic memory indexes."""


def distill_episodes_nightly(batch: int = 30) -> dict:
    return {"facts": 0}


def supersede_older_fact(old_key: str, new_key: str) -> None:
    pass


def compute_backup_schedule(weekday: str = "sunday") -> str:
    return f"{weekday} 03:00"
