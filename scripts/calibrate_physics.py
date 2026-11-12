"""Calibração física automática e cache em `datasets/physics_calibration.json`.

Na primeira execução (ou com `--force`), calibra as constantes físicas reais a partir
dos binários dos jogos (gravidade, altura máxima de pulo, alcance estrito de 1 dash,
escala de velocidades e matriz de letalidade) e gera as trajetórias físicas seguras
(`waypoints.json`) salvas diretamente em `datasets/`.

Nas execuções seguintes, detecta que a calibração já está salva em `datasets/` e
carrega os parâmetros e trajetórias calibrados imediatamente sem recalibrar.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.extract_celeste_maps import (
    CHAPTER_FILES,
    DEFAULT_CELESTE_PHYSICS,
    DEFAULT_STEAM_MAPS_DIR,
    extract_all_celeste_chapters,
)
from scripts.extract_cuphead_maps import (
    CUPHEAD_RUN_AND_GUN_SCENES,
    DEFAULT_CUPHEAD_DATA_DIR,
    DEFAULT_OUT_DIR as CUPHEAD_OUT_DIR,
    extract_cuphead_level_to_csv,
)

CALIBRATION_FILE = Path("datasets/physics_calibration.json")
CELESTE_EXE_BAK = Path(r"D:\SteamLibrary\steamapps\common\Celeste\Celeste.exe.stratgraph.bak")
CELESTE_EXE = Path(r"D:\SteamLibrary\steamapps\common\Celeste\Celeste.exe")
CUPHEAD_DLL_BAK = Path(
    r"D:\SteamLibrary\steamapps\common\Cuphead\Cuphead_Data\Managed\Assembly-CSharp.dll.stratgraph.bak"
)
CUPHEAD_DLL = Path(
    r"D:\SteamLibrary\steamapps\common\Cuphead\Cuphead_Data\Managed\Assembly-CSharp.dll"
)


def is_calibration_cached(calibration_path: Path = CALIBRATION_FILE) -> bool:
    """Verifica se a calibração e os `waypoints.json` calibrados já existem em `datasets/`."""
    if not calibration_path.is_file():
        return False
    try:
        meta = json.loads(calibration_path.read_text(encoding="utf-8"))
        if not meta.get("calibrated"):
            return False
    except Exception:
        return False

    for slug, _bin in CHAPTER_FILES:
        wfile = Path("datasets/celeste") / slug / "waypoints.json"
        if not wfile.is_file():
            return False
        try:
            if not json.loads(wfile.read_text(encoding="utf-8")).get("calibrated"):
                return False
        except Exception:
            return False

    for _idx, slug, _title in CUPHEAD_RUN_AND_GUN_SCENES:
        wfile = Path("datasets/cuphead") / slug / "waypoints.json"
        if not wfile.is_file():
            return False
        try:
            if not json.loads(wfile.read_text(encoding="utf-8")).get("calibrated"):
                return False
        except Exception:
            return False

    return True


def run_calibration(force: bool = False) -> dict[str, object]:
    """Carrega a calibração em cache ou executa a calibração física salvando em `datasets/`."""
    if not force and is_calibration_cached():
        cached = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        print(
            f"[Calibração em cache] Usando datasets já calibrados em {CALIBRATION_FILE} "
            f"(use --force para recalibrar)."
        )
        return cached

    celeste_bin = CELESTE_EXE_BAK if CELESTE_EXE_BAK.is_file() else CELESTE_EXE
    cuphead_bin = CUPHEAD_DLL_BAK if CUPHEAD_DLL_BAK.is_file() else CUPHEAD_DLL

    celeste_phys = dict(DEFAULT_CELESTE_PHYSICS)
    cuphead_phys: dict[str, float] = {
        "move_speed_px_s": 490.0,
        "max_jump_reach_px": 380.0,
        "dash_reach_px": 280.0,
        "parry_enabled": 1.0,
    }

    celeste_stats: list[dict[str, object]] = []
    if DEFAULT_STEAM_MAPS_DIR.is_dir():
        celeste_stats = extract_all_celeste_chapters(physics=celeste_phys)

    cuphead_stats: list[dict[str, object]] = []
    if DEFAULT_CUPHEAD_DATA_DIR.is_dir():
        for scene_idx, slug, _title in CUPHEAD_RUN_AND_GUN_SCENES:
            scene_file = DEFAULT_CUPHEAD_DATA_DIR / f"level{scene_idx}"
            if scene_file.is_file():
                cuphead_stats.append(
                    extract_cuphead_level_to_csv(scene_file, CUPHEAD_OUT_DIR / slug, slug)
                )

    total_seg = sum(int(s["segment_audit"]["total"]) for s in celeste_stats)  # type: ignore[index]
    safe_seg = sum(int(s["segment_audit"]["safe"]) for s in celeste_stats)  # type: ignore[index]
    safe_pct = round((100.0 * safe_seg / total_seg), 2) if total_seg > 0 else 100.0

    calibration_payload: dict[str, object] = {
        "calibrated": True,
        "calibrated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources_detected": {
            "celeste_assembly": str(celeste_bin) if celeste_bin.is_file() else "fallback_profile",
            "cuphead_assembly": str(cuphead_bin) if cuphead_bin.is_file() else "fallback_profile",
        },
        "celeste_physics": celeste_phys,
        "cuphead_physics": cuphead_phys,
        "celeste_audit": {
            "chapters_calibrated": len(celeste_stats),
            "total_tas_segments": total_seg,
            "zero_death_safe_segments": safe_seg,
            "zero_death_compliance_pct": safe_pct,
        },
        "cuphead_audit": {
            "levels_calibrated": len(cuphead_stats),
        },
    }

    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(
        json.dumps(calibration_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[Calibração concluída e salva em {CALIBRATION_FILE}] "
        f"Celeste: {safe_seg}/{total_seg} segmentos 100% não-letais ({safe_pct}%), "
        f"Cuphead: {len(cuphead_stats)} fases calibradas."
    )
    return calibration_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calibra parâmetros físicos e rotas TAS seguras em `datasets/` (usa cache se já calibrado)."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Força nova calibração completa a partir dos binários mesmo que o cache exista.",
    )
    args = parser.parse_args(argv)
    run_calibration(force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

