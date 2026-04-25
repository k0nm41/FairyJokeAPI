#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.append(str(Path(".").resolve()))

from app import db
from app.api.games.sdvx.models import (
    Apeca,
    ApecaImport,
    Difficulties,
    Difficulty,
    DifficultyImport,
    Music,
)
from app.models import Game, ImportBatch, Series, Version

target = Path(sys.argv[1])
MUSIC_FOLDER = target.parent / ".." / "music"
if not MUSIC_FOLDER.exists():
    print("music folder not found")
    MUSIC_FOLDER = False


def get(node: ET.Element, key: str, coerce=str):
    return coerce(node.get(key) or node.find(key).text)


NABLA_INITIAL_DATECODE = "2025122400"

TRANSLATION_TABLE = {
    "龕": "€",
    "釁": "🍄",
    "驩": "Ø",
    "曦": "à",
    "齷": "é",
    "骭": "ü",
    "齶": "♡",
    "彜": "ū",
    "罇": "ê",
    "雋": "Ǜ",
    "鬻": "♃",
    "鬥": "Ã",
    "鬆": "Ý",
    "曩": "è",
    "驫": "ā",
    "齲": "♥",
    "騫": "á",
    "趁": "Ǣ",
    "鬮": "¡",
    "盥": "⚙︎",
    "隍": "︎Ü",
    "頽": "ä",
    "餮": "Ƶ",
    "黻": "*",
    "蔕": "ũ",
    "闃": "Ā",
    "饌": "²",
    "煢": "ø",
    "鑷": "ゔ",
    "=墸Σ": "=͟͟͞ Σ",
    "鹹": "Ĥ",
    "瀑i": "Ài",
    "疉": "Ö",
    "鑒": "₩",
    "Ryu??": "Ryu☆",
    "壥": "Є",
}


def translate(x: str):
    for old, new in TRANSLATION_TABLE.items():
        x = x.replace(old, new)
    return x


def bpmify(x: str):
    return int(x) / 100


def dateify(x: str):
    return date.fromisoformat(f"{x[0:4]}-{x[4:6]}-{x[6:8]}")


def diffify(x: str):
    return {
        "2": Difficulties.INF,
        "3": Difficulties.GRV,
        "4": Difficulties.HVN,
        "5": Difficulties.VVD,
        "6": Difficulties.XCD,
    }.get(x)


def parse_music_db(tree, batch):
    for tag in tree:
        info: ET.Element = tag.find("info")
        music_id = get(tag, "id", int)
        music = db.create(
            Music,
            {"id": music_id},
            {
                # removed in 2025-11-19
                # "label": get(info, "label"),
                "title": get(info, "title_name"),
                "title_yomigana": get(info, "title_yomigana"),
                "artist": get(info, "artist_name"),
                "artist_yomigana": get(info, "artist_yomigana"),
                "ascii": get(info, "ascii"),
                "bpm_min": get(info, "bpm_min", bpmify),
                "bpm_max": get(info, "bpm_max", bpmify),
                "release_date": get(info, "distribution_date", dateify),
                "background_type": get(info, "bg_no", int),
                "genre_mask": get(info, "genre", int),
                "extra_difficulty": get(info, "inf_ver", diffify),
                "version": get(info, "version", int),
            },
            commit=False,
            update=True,
        )
        diffs = tag.find("difficulty")
        jacket_id = 1
        for diff in diffs:
            level = get(diff, "difnum", int)
            if not level:
                continue

            # nabla
            if batch.version.name >= NABLA_INITIAL_DATECODE:
                level = level / 10

            difficulty = db.create(
                Difficulty,
                {
                    "music_id": music_id,
                    "diff": (
                        Difficulties(diff.tag.upper())
                        if diff.tag != "infinite"
                        else music.extra_difficulty
                    ),
                },
                {
                    "level": level,
                    "illustrator": get(diff, "illustrator"),
                    "effector": get(diff, "effected_by"),
                },
                commit=False,
                update=True,
            )
            if MUSIC_FOLDER:
                folder = MUSIC_FOLDER / music.folder
                this_jacket = int(difficulty.diff)
                if (
                    folder / difficulty.get_filename(jacket_id=this_jacket)
                ).exists():
                    jacket_id = this_jacket
                difficulty.jacket_id = jacket_id
                difficulty.has_internal_jacket = True
            db.add(
                DifficultyImport,
                batch=batch,
                difficulty=difficulty,
                commit=False,
            )


def parse_apecas(tree, batch):
    for tag in tree:
        info: ET.Element = tag.find("info")
        card_id = get(tag, "id", int)
        apeca = db.create(
            Apeca,
            {"id": card_id},
            {
                "title": get(info, "title"),
                "texture": get(info, "texture"),
                "illustrator": get(info, "illustrator"),
                "rarity": get(info, "rarity", int),
                "sort": get(info, "sort_no", int),
                "generator": get(info, "generator_no", int),
                "genre": get(info, "genre", int),
                "messages": {c: get(info, f"message_{c}") for c in "abcdefgh"},
            },
            commit=False,
        )
        db.add(ApecaImport, batch=batch, apeca=apeca, commit=False)


if __name__ == "__main__":
    text = target.read_text(encoding="cp932", errors="ignore")
    text = translate(text)
    tree = ET.fromstring(text)
    fun = {
        "music_db": parse_music_db,
        "appeal_card": parse_apecas,
    }.get(target.stem)
    if not fun:
        raise Exception("Unsupported")

    game_name = sys.argv[2]
    for folder in target.parents:
        if folder.stem.startswith("KFC-"):
            datecode = folder.stem.split("-")[-1]
            break
    else:
        datecode = sys.argv[3]
    print(f"{datecode=}")
    series = db.session.query(Series).filter_by(short="sdvx").one()
    game = (
        db.session.query(Game).filter_by(short=game_name, series=series).one()
    )
    version = db.create(Version, name=datecode, game=game)
    batch = db.add(ImportBatch, version=version, commit=False)
    fun(tree, batch)
    db.session.commit()
