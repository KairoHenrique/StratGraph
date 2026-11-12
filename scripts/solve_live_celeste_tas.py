"""Sintetizador Closed-Loop de CelesteTAS dirigido em tempo real pelo StratGraph (`src/`).

Executa o algoritmo real do StratGraph (`load_graph_from_csv`, `contract_dead_ends`,
`build_layered_graph`, `run_dijkstra`) para obter a rota ótima estratégica de
salas e itens, expande os becos contraídos em transições adjacentes reais via `.bin`
e sintetiza cada sala em malha fechada contra o jogo *Celeste* ao vivo (`Everest` +
`CelesteTAS` DebugRC em `http://localhost:32270/`) usando `ClearState` + `SaveState`
rolantes.

Respeita integralmente as regras do jogo real:
  - 1 único dash (`Player.Dashes`), recarregado apenas em solo/mola/refill;
  - mortes reais (`Level.Session.Deaths` / `Player.Dead`) podadas imediatamente;
  - colisão real de sólidos, jump-thrus, espinhos, molas, zipMovers e morangos.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from src.algorithms import run_dijkstra
from src.layered_graph import build_layered_graph
from src.loader import load_graph_from_csv
from src.models import GameGraph
from src.preprocessing import contract_dead_ends

from scripts.celeste_sim import (
    Rect,
    RoomModel60Hz,
    SimPlayer,
    compute_doorway_targets,
    plan_to_goal_60hz,
    step_celeste_60hz,
)
from scripts.export_celeste_tas import CHAPTER_AREA_IDS, validate_celestetas_script
from scripts.extract_celeste_maps import DEFAULT_STEAM_MAPS_DIR, CHAPTER_FILES, parse_celeste_bin

DEFAULT_DEBUG_RC = "http://localhost:32270"
DEFAULT_SCRATCH_TAS = Path(tempfile.gettempdir()) / "stratgraph_live_work.tas"


def _canonical_room(name: str) -> str:
    clean = name.strip()
    if not clean:
        return ""
    return clean if clean.startswith("lvl_") else f"lvl_{clean}"


def format_tas_line(frames: int, tokens: tuple[str, ...]) -> str:
    """Formata uma linha no padrão estrito CelesteTAS (`  12,R,J`)."""
    if not tokens:
        return f"{frames:4d}"
    return f"{frames:4d}," + ",".join(tokens)


def ops_to_lines(ops: list[tuple[int, tuple[str, ...]]]) -> list[str]:
    return [format_tas_line(n, toks) for n, toks in ops if n > 0]


@dataclass(frozen=True, slots=True)
class CollectibleTarget:
    uid: str
    kind: str
    room_id: str
    world_x: float
    world_y: float
    winged: bool

    @property
    def rect(self) -> Rect:
        return Rect(self.world_x - 6.0, self.world_y - 6.0, 12.0, 12.0)


@dataclass(slots=True)
class RoomMeta:
    room_id: str
    bounds: tuple[int, int, int, int]
    entities: list[tuple[str, dict]]
    collectibles: list[CollectibleTarget]


def load_chapter_metadata(bin_path: Path) -> dict[str, RoomMeta]:
    """Carrega bounds exatos e entidades (`strawberry`, `cassette`, etc.) do `.bin`."""
    _, root = parse_celeste_bin(bin_path)
    levels_node = [c for c in root[2] if c[0] == "levels"][0][2]
    rooms: dict[str, RoomMeta] = {}
    for lvl in levels_node:
        attrs = lvl[1]
        rid = _canonical_room(str(attrs.get("name", "")))
        bx = int(attrs.get("x", 0))
        by = int(attrs.get("y", 0))
        bw = int(attrs.get("width", 320))
        bh = int(attrs.get("height", 184))
        bounds = (bx, by, bw, bh)
        ents: list[tuple[str, dict]] = []
        collectibles: list[CollectibleTarget] = []
        for ch in lvl[2]:
            if ch[0] != "entities":
                continue
            for ent in ch[2]:
                ename = str(ent[0])
                eattrs = dict(ent[1])
                ents.append((ename, eattrs))
                if ename in ("strawberry", "cassette"):
                    ex = float(eattrs.get("x", 0.0))
                    ey = float(eattrs.get("y", 0.0))
                    winged = bool(eattrs.get("winged", False))
                    uid = f"{rid}:{ename}:{int(round(ex))}:{int(round(ey))}"
                    collectibles.append(
                        CollectibleTarget(
                            uid=uid,
                            kind=ename,
                            room_id=rid,
                            world_x=bx + ex,
                            world_y=by + ey,
                            winged=winged,
                        )
                    )
        rooms[rid] = RoomMeta(rid, bounds, ents, collectibles)
    return rooms


def expand_stratgraph_room_walk(
    raw_graph: GameGraph,
    reduced_graph: GameGraph,
    layered_path: list,
) -> list[str]:
    """Expande a rota StratGraph em saltos fisicamente adjacentes sala-a-sala."""
    # Deduplica visitas consecutivas da mesma sala na transição de camada (ex: lvl_10a L0->L1)
    spine: list[str] = []
    for node in layered_path:
        if not spine or spine[-1] != node.room_id:
            spine.append(node.room_id)

    adj_set: dict[str, list[str]] = {
        u: [e.destination for e in edges]
        for u, edges in raw_graph.adjacency.items()
    }
    contracted_into = reduced_graph.contracted_into

    full_walk: list[str] = []

    def _append_room(r: str) -> None:
        if not full_walk or full_walk[-1] != r:
            full_walk.append(r)

    def _visit_subtree(root: str, allowed_sub: set[str], visited_sub: set[str]) -> None:
        visited_sub.add(root)
        _append_room(root)
        for nxt in adj_set.get(root, []):
            if nxt in allowed_sub and nxt not in visited_sub:
                _visit_subtree(nxt, allowed_sub, visited_sub)
                _append_room(root)

    for rid in spine:
        sub = set(contracted_into.get(rid, ()))
        if sub:
            _visit_subtree(rid, sub, set())
        else:
            _append_room(rid)

    return full_walk


@dataclass(slots=True)
class LiveSnapshot:
    running: bool
    paused: bool
    current_frame: int
    total_frames: int
    room_name: str
    deaths: int
    berries: int
    dashes: int
    dead: bool
    cassette: bool
    followers: int
    stamina: float
    pre: str


class CelesteTASClient:
    """Cliente HTTP para Everest DebugRC + CelesteTAS com SaveStates rolantes."""

    def __init__(self, base_url: str = DEFAULT_DEBUG_RC, work_file: Path = DEFAULT_SCRATCH_TAS) -> None:
        self.base_url = base_url.rstrip("/")
        self.work_file = work_file
        self.work_file.parent.mkdir(parents=True, exist_ok=True)
        self._custominfo_configured = False

    def _get(self, path: str, timeout: float = 5.0) -> str:
        with urllib.request.urlopen(self.base_url + path, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "ignore")

    def ensure_ready(self) -> None:
        try:
            self._get("/tas/info", timeout=3.0)
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"DebugRC nao respondeu em {self.base_url}. "
                "Abra o Celeste com Everest + CelesteTAS ativos."
            ) from exc

        if not self._custominfo_configured:
            tpl = (
                "SG|Deaths:{Level.Session.Deaths}"
                "|Berries:{Level.Session.Strawberries.Count}"
                "|Dashes:{Player.Dashes}"
                "|Dead:{Player.Dead}"
                "|Cassette:{Level.Session.Cassette}"
                "|Followers:{Player.Leader.Followers.Count}"
            )
            self._get("/tas/custominfo?template=" + urllib.parse.quote(tpl))
            self._custominfo_configured = True

    def clear_state(self) -> None:
        self._get("/tas/sendhotkey?id=ClearState")
        time.sleep(0.03)

    def save_state(self) -> None:
        self._get("/tas/sendhotkey?id=SaveState")
        time.sleep(0.05)

    def get_info(self) -> LiveSnapshot:
        html = self._get("/tas/info", timeout=3.0)
        running = "Running: True" in html
        paused = "State: Paused" in html
        m_cf = re.search(r"CurrentFrame:\s*(\d+)", html)
        m_tf = re.search(r"TotalFrames:\s*(\d+)", html)
        m_rn = re.search(r"RoomName:\s*([^\r\n<]+)", html)
        cf = int(m_cf.group(1)) if m_cf else 0
        tf = int(m_tf.group(1)) if m_tf else 0
        pre = html.split("<pre>")[-1].split("</pre>")[0] if "<pre>" in html else ""

        rn = _canonical_room(m_rn.group(1)) if m_rn else ""
        if not rn:
            m_pre_rn = re.search(r"\[([^\]]+)\]\s*Timer:", pre)
            if m_pre_rn:
                rn = _canonical_room(m_pre_rn.group(1))

        def _int_tag(tag: str, default: int = 0) -> int:
            m = re.search(rf"{tag}:(-?\d+)", pre)
            return int(m.group(1)) if m else default

        def _bool_tag(tag: str) -> bool:
            m = re.search(rf"{tag}:(True|False)", pre)
            return m.group(1) == "True" if m else False

        m_stam = re.search(r"Stamina:\s*([\d.]+)", pre)
        stamina = float(m_stam.group(1)) if m_stam else 110.0

        return LiveSnapshot(
            running=running,
            paused=paused,
            current_frame=cf,
            total_frames=tf,
            room_name=rn,
            deaths=_int_tag("Deaths", 0),
            berries=_int_tag("Berries", 0),
            dashes=_int_tag("Dashes", 1),
            dead=_bool_tag("Dead") or ("Dead" in pre and "Dead:False" not in pre),
            cassette=_bool_tag("Cassette"),
            followers=_int_tag("Followers", 0),
            stamina=stamina,
            pre=pre,
        )

    def get_game_state(self) -> dict | None:
        raw = self._get("/tas/game_state", timeout=3.0).strip()
        if not raw:
            return None
        try:
            gs = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return gs if isinstance(gs, dict) and "Player" in gs else None

    def run_tas_and_wait(
        self,
        header_cmd: str,
        body_lines: list[str],
        expected_total_frames: int,
        timeout: float = 8.0,
    ) -> tuple[LiveSnapshot, dict | None]:
        """Executa o script até `expected_total_frames` usando fast-forward + SaveState."""
        body_txt = "\n".join(body_lines)
        script = (
            "RecordCount: 1\n"
            "Unsafe\n"
            "Set, CelesteTAS.FastForwardSpeed, 60\n"
            "Set, CelesteTAS.AutoPauseDraft, true\n"
            "***\n"
            f"{header_cmd}\n"
            f"{body_txt}\n"
            "***\n"
        )
        for attempt in range(15):
            try:
                self.work_file.write_text(script, encoding="utf-8")
                break
            except PermissionError:
                if attempt == 14:
                    raise
                time.sleep(0.025)
        self._get("/tas/playtas?filePath=" + urllib.parse.quote(str(self.work_file)), timeout=5.0)
        time.sleep(0.03)

        t0 = time.monotonic()
        last_snap: LiveSnapshot | None = None
        while time.monotonic() - t0 < timeout:
            snap = self.get_info()
            last_snap = snap
            if snap.running and snap.paused and snap.total_frames == expected_total_frames and snap.current_frame >= expected_total_frames:
                gs = self.get_game_state()
                if gs and gs.get("RoomName"):
                    snap.room_name = _canonical_room(str(gs["RoomName"]))
                return snap, gs
            time.sleep(0.015)

        gs = self.get_game_state()
        assert last_snap is not None
        return last_snap, gs


def _pick_safe_horizon(
    room: RoomModel60Hz,
    sim_start: SimPlayer,
    ops: list[tuple[int, tuple[str, ...]]],
    min_fr: int = 34,
    max_fr: int = 185,
) -> int:
    """Escolhe horizonte de corte seguro (prefere pousar em solo ou completar arco <= max_fr)."""
    total = sum(n for n, _ in ops)
    if total <= 90:
        return total

    cur = sim_start
    pj = pd = False
    f_idx = 0
    last_ground = 0
    for n, toks in ops:
        for _ in range(n):
            cur, pj, pd = step_celeste_60hz(room, cur, toks, pj, pd)
            f_idx += 1
            if cur.dead:
                return last_ground if last_ground > 0 else max(12, f_idx - 12)
            if cur.on_ground and f_idx >= min_fr:
                last_ground = f_idx
                if f_idx >= 60:
                    return f_idx
            if f_idx >= max_fr:
                return last_ground if last_ground >= min_fr else max_fr
    return total


def _safe_landing_rects(room: RoomModel60Hz) -> list[Rect]:
    """Identifica plataformas sólidas livres de espinhos para concluir coleta de morangos."""
    rects: list[Rect] = []
    for r in range(1, room.ht):
        for c in range(1, room.wt - 1):
            if room.solids[r][c] and not room.solids[r - 1][c]:
                px = room.bx + c * 8.0 + 4.0
                py = room.by + r * 8.0
                if not room.is_lethal(px, py, 0.0, 0.0):
                    rects.append(Rect(px - 6.0, py - 12.0, 12.0, 12.0))
    for jt in room.jump_thrus:
        px = jt.x + jt.w * 0.5
        py = jt.y
        if not room.is_lethal(px, py, 0.0, 0.0):
            rects.append(Rect(jt.x + 2.0, jt.y - 12.0, max(8.0, jt.w - 4.0), 12.0))
    return rects


def _has_safe_continuation(room: RoomModel60Hz, gs: dict, dashes: int, horizon: int = 16) -> bool:
    """Verifica offline se há ao menos uma ação trivial que não cai direto em morte súbita."""
    base = SimPlayer.from_game_state(gs, dashes=dashes, stamina=110.0)
    if base.on_ground:
        return True
    probes: list[tuple[str, ...]] = [(), ("L",), ("R",), ("L", "U", "G"), ("R", "U", "G")]
    if dashes >= 1:
        probes.extend([("R", "U", "X"), ("L", "U", "X"), ("U", "X")])
    for toks in probes:
        cur = base
        pj = pd = False
        survived = True
        for f in range(horizon):
            t_use = toks if ("X" not in toks or f == 0) else tuple(t for t in toks if t != "X")
            cur, pj, pd = step_celeste_60hz(room, cur, t_use, pj, pd)
            if cur.dead:
                survived = False
                break
        if survived:
            return True
    return False


def _split_ops_prefix(ops: list[tuple[int, tuple[str, ...]]], max_frames: int) -> list[tuple[int, tuple[str, ...]]]:
    """Recorta os primeiros `max_frames` de uma sequência de ops."""
    out: list[tuple[int, tuple[str, ...]]] = []
    rem = max_frames
    for n, toks in ops:
        if rem <= 0:
            break
        take = min(n, rem)
        if take > 0:
            out.append((take, toks))
            rem -= take
    return out


def _eval_plan_in_live(
    client: CelesteTASClient,
    header_cmd: str,
    committed_lines: list[str],
    committed_frames: int,
    base_deaths: int,
    ops: list[tuple[int, tuple[str, ...]]],
    chunk_limit: int = 38,
    expected_room: str = "",
) -> tuple[bool, int, list[str], LiveSnapshot, dict | None, bool]:
    """Executa `ops` em fatias curtas no jogo real; aborta se morrer no caminho.

    Retorna `(alive, total_frames_executed, new_lines, snap, gs, transitioned_or_stopped)`.
    """
    cur_lines = list(committed_lines)
    cur_frames = committed_frames
    rem_ops = list(ops)
    added_lines: list[str] = []

    while rem_ops:
        slice_ops = _split_ops_prefix(rem_ops, chunk_limit)
        slice_fr = sum(n for n, _ in slice_ops)
        if slice_fr == 0:
            break

        # Consome `slice_fr` de `rem_ops`
        left_to_consume = slice_fr
        next_rem: list[tuple[int, tuple[str, ...]]] = []
        for n, toks in rem_ops:
            if left_to_consume <= 0:
                next_rem.append((n, toks))
            elif n <= left_to_consume:
                left_to_consume -= n
            else:
                next_rem.append((n - left_to_consume, toks))
                left_to_consume = 0
        rem_ops = next_rem

        sl_lines = ops_to_lines(slice_ops)
        cur_lines.extend(sl_lines)
        added_lines.extend(sl_lines)
        cur_frames += slice_fr

        snap, gs = client.run_tas_and_wait(header_cmd, cur_lines, cur_frames)
        if snap.dead or snap.deaths > base_deaths or gs is None:
            return False, cur_frames - committed_frames, added_lines, snap, gs, True

        # Se mudou de sala ou entrou em cutscene/transição durante essa fatia, para aqui para estabilizar
        res_room = _canonical_room(str(gs.get("RoomName", "")))
        if (expected_room and res_room != expected_room) or gs.get("PlayerStateName") in ("StDummy", "StIntroRespawn"):
            return True, cur_frames - committed_frames, added_lines, snap, gs, True

    return True, cur_frames - committed_frames, added_lines, snap, gs, False


def _stabilize_after_transition(
    client: CelesteTASClient,
    header_cmd: str,
    committed_lines: list[str],
    committed_frames: int,
    base_deaths: int,
    entry_gs: dict,
    target_room: str,
) -> tuple[list[str], int, LiveSnapshot, dict]:
    """Avança quadros vazios até a transição de câmera terminar e a Madeline voltar a se mover."""
    lines = list(committed_lines)
    frames = committed_frames
    ex0 = float(entry_gs["Player"]["Position"]["X"])
    ey0 = float(entry_gs["Player"]["Position"]["Y"])
    last_snap = client.get_info()
    last_gs = entry_gs
    transition_finished = False

    for _ in range(16):
        lines.append("   3")
        frames += 3
        snap2, gs2 = client.run_tas_and_wait(header_cmd, lines, frames)
        if snap2.dead or snap2.deaths > base_deaths or gs2 is None:
            lines.pop()
            frames -= 3
            break
        r2 = _canonical_room(str(gs2.get("RoomName", "")))
        if r2 != target_room:
            lines.pop()
            frames -= 3
            break
        last_snap, last_gs = snap2, gs2
        px = float(gs2["Player"]["Position"]["X"])
        py = float(gs2["Player"]["Position"]["Y"])
        if not transition_finished and (abs(px - ex0) > 0.5 or abs(py - ey0) > 0.5):
            transition_finished = True
        if transition_finished and (gs2["Player"].get("OnGround", False) or abs(py - ey0) >= 6.0):
            return lines, frames, last_snap, last_gs

    return lines, frames, last_snap, last_gs


def _live_micro_probes(
    sim: SimPlayer,
    prefer_dx: float,
    prefer_dy: float,
    forbid_dash: bool,
) -> list[list[tuple[int, tuple[str, ...]]]]:
    """Sequências curtas de fallback testadas diretamente no motor real do jogo."""
    d = "R" if prefer_dx >= 0 else "L"
    opp = "L" if d == "R" else "R"
    probes: list[list[tuple[int, tuple[str, ...]]]] = [
        [(14, (d, "J")), (10, (d,))],
        [(8, (d, "J")), (8, (d,))],
        [(18, (d,))],
        [(14, (d, "J")), (12, (d, "U", "G"))],
        [(12, (opp, "J")), (10, (opp,))],
        [(12, (d, "D"))],
        [(10, ())],
        [(15, ("J",))],
    ]
    if not sim.on_ground:
        probes.extend([[(26, ())], [(24, (d,))], [(24, (opp,))]])
    if sim.dashes >= 1 and not forbid_dash:
        dash_opts = [("R", "U"), ("L", "U"), ("U",), ("R",), ("L",)]
        dash_opts.sort(
            key=lambda dt: -(
                (1 if "R" in dt else (-1 if "L" in dt else 0)) * prefer_dx
                + (-1 if "U" in dt else 0) * prefer_dy
            )
        )
        if abs(prefer_dy) <= 36.0 and (d,) not in dash_opts[:3]:
            dash_opts.insert(0, (d,))
        for dt in dash_opts[:4]:
            lr = tuple(t for t in dt if t in ("L", "R"))
            probes.insert(1, [(1, (*dt, "X")), (13, dt), (10, lr)])
            probes.insert(2, [(1, (*dt, "X")), (13, dt), (10, (*lr, "U", "G"))])
    return probes


def solve_chapter_live(
    dataset_dir: Path,
    alpha: float,
    out_path: Path,
    install_path: Path | None,
    max_rooms: int | None = None,
    area_id: int = 1,
    allow_room_checkpoints: bool = True,
    report_path: Path | None = None,
) -> dict:
    """Executa o sintetizador closed-loop StratGraph <-> Celeste ao vivo."""
    raw_graph = load_graph_from_csv(dataset_dir)
    reduced_graph = contract_dead_ends(raw_graph)
    layered = build_layered_graph(reduced_graph, alpha=alpha)
    dijkstra_res = run_dijkstra(layered)

    chapter_key = dataset_dir.name
    bin_name = dict(CHAPTER_FILES).get(chapter_key)
    if not bin_name:
        raise ValueError(f"Capitulo sem mapeamento .bin: {chapter_key}")
    bin_path = DEFAULT_STEAM_MAPS_DIR / bin_name
    room_metas = load_chapter_metadata(bin_path)

    room_walk = expand_stratgraph_room_walk(raw_graph, reduced_graph, dijkstra_res.path)
    if max_rooms is not None:
        room_walk = room_walk[: max(2, max_rooms)]

    client = CelesteTASClient()
    client.ensure_ready()

    start_room = room_walk[0]
    short_start = start_room.removeprefix("lvl_")
    header_cmd = f"console load {area_id} {short_start}"

    client.clear_state()
    committed_lines: list[str] = ["  95"]
    committed_frames = 95
    snap, gs = client.run_tas_and_wait(header_cmd, committed_lines, committed_frames)
    if gs is None:
        raise RuntimeError("Falha ao inicializar sala inicial via console load.")
    client.save_state()

    base_deaths = snap.deaths
    seg_berry_base = snap.berries
    prior_frames = 0
    prior_berries = 0
    prior_deaths = 0
    collected_uids: set[str] = set()
    script_sections: list[str] = [
        "# StratGraph Closed-Loop Live CelesteTAS",
        f"# Capitulo: {chapter_key} | Alpha: {alpha} | Rota Dijkstra: {len(dijkstra_res.path)} nos ({dijkstra_res.collectibles_count} coletaveis teoricos)",
        f"# Walk expandido ({len(room_walk)} visitas): {' -> '.join(room_walk)}",
        "",
        "RecordCount: 1",
        "Unsafe",
        "",
        f"console load {area_id} {short_start}",
        "  95",
    ]
    room_visit_counts: dict[str, int] = {start_room: 1}
    rooms_cleared: list[str] = []
    continuous_transitions = 0
    checkpoint_resumes: list[str] = []

    print(
        f"[StratGraph] Iniciando sintese live: {len(room_walk)} salas | "
        f"start={snap.room_name} pos=({gs['Player']['Position']['X']},{gs['Player']['Position']['Y']}) "
        f"deaths={base_deaths}"
    )

    for step_idx in range(len(room_walk) - 1):
        cur_rid = room_walk[step_idx]
        nxt_rid = room_walk[step_idx + 1]
        cur_meta = room_metas[cur_rid]
        nxt_meta = room_metas[nxt_rid]

        # Garante que estamos na sala esperada ou sincroniza caso já tenha cruzado
        snap_now = client.get_info()
        gs_now = client.get_game_state()
        if gs_now is None or _canonical_room(str(gs_now.get("RoomName", ""))) != cur_rid:
            print(f"  [Aviso] Sala atual {_canonical_room(str((gs_now or {}).get('RoomName', '')))} != esperada {cur_rid}; interrompendo continuidade.")
            break

        # Sub-objetivos na sala atual: 1) coletáveis pendentes da sala, 2) porta para nxt_rid
        pending_collectibles = [
            c for c in cur_meta.collectibles if c.uid not in collected_uids
        ]
        objectives: list[tuple[str, list[Rect], bool, CollectibleTarget | None]] = []
        for col in pending_collectibles:
            objectives.append((f"coletar {col.uid}", [col.rect], col.winged, col))

        model0 = RoomModel60Hz.from_game_state(gs_now, cur_meta.entities)
        door_rects = compute_doorway_targets(cur_meta.bounds, nxt_meta.bounds, model0)
        objectives.append((f"porta -> {nxt_rid}", door_rects, False, None))

        visit_n = room_visit_counts.get(cur_rid, 1)
        label = f"#{cur_rid}" if visit_n == 1 else f"#{cur_rid} (v{visit_n})"
        script_sections.append(label)

        room_ok = True
        for obj_label, goal_rects, forbid_dash, col_obj in objectives:
            # Verifica se há morango alado ainda não coletado antes da saída -> proíbe dash durante coletas
            has_uncollected_winged = any(
                c.winged and c.uid not in collected_uids for c in cur_meta.collectibles
            )
            eff_forbid_dash = (forbid_dash or has_uncollected_winged) if col_obj is not None else forbid_dash

            print(f"  [{cur_rid}] Objetivo: {obj_label} (forbid_dash={eff_forbid_dash})")
            obj_done = False
            obj_start_snap = client.get_info()
            ground_ckpt = (list(committed_lines), committed_frames, len(script_sections), set(collected_uids))
            touched_follower = False
            banned_at_frame: dict[int, set[tuple[str, ...]]] = {}
            banned_states: set[tuple[int, int, int]] = set()
            last_chosen_sig: tuple[int, tuple[str, ...]] | None = None
            last_chosen_state: tuple[int, int, int] | None = None
            rollbacks_used = 0

            for it in range(36):
                gs_now = client.get_game_state()
                snap_now = client.get_info()
                if gs_now is None:
                    break
                live_room = _canonical_room(str(gs_now.get("RoomName", "")))
                if col_obj is None and live_room == nxt_rid:
                    obj_done = True
                    break

                if col_obj is not None and (
                    (col_obj.kind == "strawberry" and snap_now.berries > obj_start_snap.berries)
                    or (col_obj.kind == "cassette" and snap_now.cassette and not obj_start_snap.cassette)
                ):
                    collected_uids.add(col_obj.uid)
                    print(f"    -> Coleta confirmada no jogo: {col_obj.uid} (berries={snap_now.berries})")
                    obj_done = True
                    break

                room_model = RoomModel60Hz.from_game_state(gs_now, cur_meta.entities)
                sim = SimPlayer.from_game_state(
                    gs_now,
                    dashes=snap_now.dashes,
                    stamina=snap_now.stamina,
                )
                if gs_now["Player"].get("OnGround", False):
                    ground_ckpt = (list(committed_lines), committed_frames, len(script_sections), set(collected_uids))

                active_goals = list(goal_rects)
                if col_obj is not None and (
                    snap_now.followers > obj_start_snap.followers
                    or touched_follower
                    or col_obj.rect.overlaps(sim.x - 4.0, sim.y - 11.0, 8.0, 11.0)
                ):
                    touched_follower = True
                    if col_obj.kind == "cassette":
                        collected_uids.add(col_obj.uid)
                        obj_done = True
                        break
                    # Tocou o morango: agora precisa pousar em solo seguro para efetivar a coleta
                    safe_rects = _safe_landing_rects(room_model)
                    if safe_rects:
                        active_goals = safe_rects

                centers = [(g.x + g.w * 0.5, g.y + g.h * 0.5) for g in active_goals]
                field = room_model.bfs_distance_field(centers)
                c0 = min(centers, key=lambda c: (c[0] - sim.x) ** 2 + (c[1] - sim.y) ** 2)
                cur_h = room_model.heuristic_dist(sim.x, sim.y, field, c0)

                plans = plan_to_goal_60hz(
                    room_model,
                    sim,
                    active_goals,
                    max_expansions=4500,
                    max_frames=460,
                    diverse_count=4,
                    forbid_dash=eff_forbid_dash,
                )
                # Também tenta waypoint intermediário BFS caso o plano direto tenha custo alto/nenhum hit
                waypoints = room_model.extract_bfs_waypoints((sim.x, sim.y), field, step_tiles=8)
                candidates: list[list[tuple[int, tuple[str, ...]]]] = list(plans)
                if waypoints:
                    wp = waypoints[0]
                    wp_plans = plan_to_goal_60hz(
                        room_model,
                        sim,
                        Rect(wp[0] - 8.0, wp[1] - 8.0, 16.0, 16.0),
                        max_expansions=1500,
                        max_frames=180,
                        diverse_count=2,
                        forbid_dash=eff_forbid_dash,
                    )
                    candidates.extend(wp_plans)

                # Adiciona micro-probes de fallback ao vivo no final da fila de tentativas
                tagged_cands: list[tuple[bool, list[tuple[int, tuple[str, ...]]]]] = [
                    (idx < len(plans), c) for idx, c in enumerate(candidates)
                ]
                tagged_cands.extend(
                    (False, probe)
                    for probe in _live_micro_probes(sim, c0[0] - sim.x, c0[1] - sim.y, eff_forbid_dash)
                )
                if touched_follower:
                    if sim.on_ground:
                        tagged_cands.insert(0, (True, [(16, ())]))
                    else:
                        d_land = "R" if (c0[0] - sim.x) >= 0 else "L"
                        tagged_cands.insert(0, (True, [(28, ())]))
                        tagged_cands.insert(1, (True, [(26, (d_land,))]))

                committed_step = False
                # score = eff_h (menor = melhor); tupla guarda (eff_h, new_h, delta_fr, new_lines, sn_res, gs_res, touched_now, cand_sig)
                best_progress: tuple[float, float, int, list[str], LiveSnapshot, dict, bool, tuple[str, ...]] | None = None
                banned_here = banned_at_frame.get(committed_frames, set())
                for cand_idx, (is_direct_plan, cand_ops) in enumerate(tagged_cands):
                    if not cand_ops:
                        continue
                    horizon = sum(n for n, _ in cand_ops)
                    if is_direct_plan and horizon <= 95:
                        cut_fr = horizon
                    else:
                        cut_fr = _pick_safe_horizon(room_model, sim, cand_ops, min_fr=24, max_fr=85)
                    test_ops = _split_ops_prefix(cand_ops, cut_fr)
                    cand_sig = tuple(ops_to_lines(test_ops))
                    if cand_sig in banned_here:
                        continue
                    alive, delta_fr, new_lines, sn_res, gs_res, _ = _eval_plan_in_live(
                        client,
                        header_cmd,
                        committed_lines,
                        committed_frames,
                        base_deaths,
                        test_ops,
                        chunk_limit=22,
                        expected_room=cur_rid,
                    )
                    if not alive or gs_res is None:
                        continue

                    res_room = _canonical_room(str(gs_res.get("RoomName", "")))
                    # Mudou para sala desejada!
                    if col_obj is None and res_room == nxt_rid:
                        committed_lines.extend(new_lines)
                        committed_frames += delta_fr
                        pre_stab_len = len(committed_lines)
                        committed_lines, committed_frames, sn_stab, gs_stab = _stabilize_after_transition(
                            client, header_cmd, committed_lines, committed_frames, base_deaths, gs_res, nxt_rid
                        )
                        stab_added = committed_lines[pre_stab_len:]
                        client.clear_state()
                        client.save_state()
                        script_sections.extend(new_lines)
                        script_sections.extend(stab_added)
                        obj_done = True
                        committed_step = True
                        print(f"    -> Transicao confirmada para {nxt_rid} (+{delta_fr}+{len(stab_added)*3}f, berries={sn_stab.berries}, deaths={sn_stab.deaths})")
                        break

                    # Evita voltar por acidente a sala errada
                    if res_room != cur_rid and res_room != nxt_rid:
                        continue

                    # Checa progresso real no objetivo dentro da mesma sala
                    pl_res = gs_res["Player"]
                    rx = float(pl_res["Position"]["X"]) + float(pl_res.get("PositionRemainder", {}).get("X", 0.0))
                    ry = float(pl_res["Position"]["Y"]) + float(pl_res.get("PositionRemainder", {}).get("Y", 0.0))
                    if (committed_frames + delta_fr, round(rx), round(ry)) in banned_states:
                        continue
                    rc_best = min(centers, key=lambda c: (c[0] - rx) ** 2 + (c[1] - ry) ** 2)
                    new_h = room_model.heuristic_dist(rx, ry, field, rc_best)
                    is_grounded = bool(pl_res.get("OnGround", False))

                    if col_obj is not None and (
                        (col_obj.kind == "strawberry" and sn_res.berries > obj_start_snap.berries)
                        or (col_obj.kind == "cassette" and sn_res.cassette and not obj_start_snap.cassette)
                    ):
                        best_progress = (new_h - 1000.0, new_h, delta_fr, new_lines, sn_res, gs_res, True, cand_sig)
                        break

                    # Filtra estados aéreos suicidas (ex: caindo direto sobre espinhos sem dash)
                    if not is_grounded and not _has_safe_continuation(room_model, gs_res, sn_res.dashes):
                        continue

                    touched_now = (
                        col_obj is not None
                        and not touched_follower
                        and (
                            sn_res.followers > obj_start_snap.followers
                            or col_obj.rect.overlaps(rx - 4.0, ry - 11.0, 8.0, 11.0)
                        )
                    )
                    recharge_land = (not sim.on_ground) and is_grounded and (
                        sn_res.dashes > sim.dashes or new_h <= cur_h + 65.0
                    )
                    made_progress = (
                        touched_now
                        or (new_h < cur_h - 4.0 and is_grounded)
                        or (new_h < cur_h - 12.0)
                        or (is_grounded and new_h <= cur_h and cand_idx < 2)
                        or recharge_land
                    )

                    if made_progress:
                        dash_bonus = 45.0 if (not sim.on_ground and is_grounded and sn_res.dashes > sim.dashes) else 0.0
                        eff_score = new_h - (22.0 if is_grounded else 0.0) - dash_bonus - (400.0 if touched_now else 0.0)
                        if best_progress is None or eff_score < best_progress[0]:
                            best_progress = (eff_score, new_h, delta_fr, new_lines, sn_res, gs_res, touched_now, cand_sig)
                        # Só aceita antecipadamente se for plano A* completo com pouso seguro ou quase no alvo
                        if is_direct_plan and (is_grounded or new_h <= 18.0):
                            break

                if obj_done:
                    break
                if best_progress is not None and not committed_step:
                    _eff, new_h, delta_fr, new_lines, sn_res, gs_res, marked_collect, chosen_sig = best_progress
                    pl_res = gs_res["Player"]
                    rx = float(pl_res["Position"]["X"]) + float(pl_res.get("PositionRemainder", {}).get("X", 0.0))
                    ry = float(pl_res["Position"]["Y"]) + float(pl_res.get("PositionRemainder", {}).get("Y", 0.0))
                    if pl_res.get("OnGround", False):
                        last_chosen_sig = None
                        last_chosen_state = None
                    elif last_chosen_sig is None:
                        last_chosen_sig = (committed_frames, chosen_sig)
                        last_chosen_state = (committed_frames + delta_fr, round(rx), round(ry))
                    committed_lines.extend(new_lines)
                    committed_frames += delta_fr
                    script_sections.extend(new_lines)
                    client.clear_state()
                    sn_sync, gs_sync = client.run_tas_and_wait(header_cmd, committed_lines, committed_frames)
                    if gs_sync is not None and not sn_sync.dead:
                        gs_res, sn_res = gs_sync, sn_sync
                    client.save_state()
                    committed_step = True
                    if col_obj is not None and (
                        (col_obj.kind == "strawberry" and sn_res.berries > obj_start_snap.berries)
                        or (col_obj.kind == "cassette" and sn_res.cassette and not obj_start_snap.cassette)
                    ):
                        collected_uids.add(col_obj.uid)
                        obj_done = True
                        print(f"    -> Coleta confirmada: {col_obj.uid} em +{delta_fr}f (berries={sn_res.berries})")
                        break
                    if marked_collect:
                        touched_follower = True
                        print(f"    -> Morango tocado (seguindo): {col_obj.uid} pos=({rx:.1f},{ry:.1f}) og={pl_res.get('OnGround')}")
                    else:
                        print(f"    iter {it}: h {cur_h:.1f} -> {new_h:.1f} pos=({rx:.1f},{ry:.1f}) og={pl_res.get('OnGround')} (+{delta_fr}f)")
                if not committed_step:
                    if committed_frames > ground_ckpt[1] and (col_obj is not None or rollbacks_used < 3):
                        if last_chosen_sig is not None:
                            banned_at_frame.setdefault(last_chosen_sig[0], set()).add(last_chosen_sig[1])
                        if last_chosen_state is not None:
                            banned_states.add(last_chosen_state)
                        last_chosen_sig = None
                        last_chosen_state = None
                        committed_lines, committed_frames, sec_len, prev_uids = ground_ckpt
                        script_sections = script_sections[:sec_len]
                        collected_uids = set(prev_uids)
                        touched_follower = False
                        client.clear_state()
                        client.run_tas_and_wait(header_cmd, committed_lines, committed_frames)
                        client.save_state()
                        if col_obj is not None:
                            print(f"    [Rollback] Restaurado checkpoint em solo (f={committed_frames}); pulando {col_obj.uid}.")
                            break
                        rollbacks_used += 1
                        print(f"    [Rollback #{rollbacks_used}] Restaurado checkpoint em solo (f={committed_frames}); tentando outra rota.")
                        continue
                    print(f"    [Aviso] Sem progresso na iter {it} em {cur_rid} ({obj_label})")
                    break

            if not obj_done and col_obj is None:
                room_ok = False
                break

        if not room_ok:
            if allow_room_checkpoints:
                # Restaura ultimo estado em solo limpo antes do impasse e retoma via console load
                committed_lines, committed_frames, sec_len, prev_uids = ground_ckpt
                script_sections = script_sections[:sec_len]
                collected_uids = set(prev_uids)
                client.clear_state()
                snap_ckpt, _ = client.run_tas_and_wait(header_cmd, committed_lines, committed_frames)
                prior_frames += committed_frames
                prior_berries += max(0, snap_ckpt.berries - seg_berry_base)
                prior_deaths += max(0, snap_ckpt.deaths - base_deaths)

                short_nxt = nxt_rid.removeprefix("lvl_")
                ckpt_comment = f"# [Checkpoint StratGraph] Retomada em {nxt_rid} apos limite continuo ({cur_rid} -> {nxt_rid})"
                print(f"  [Checkpoint] {cur_rid} -> {nxt_rid} falhou continuamente; retomando via console load {area_id} {short_nxt}")
                script_sections.append(ckpt_comment)
                script_sections.append(f"console load {area_id} {short_nxt}")
                script_sections.append("  95")

                header_cmd = f"console load {area_id} {short_nxt}"
                committed_lines = ["  95"]
                committed_frames = 95
                client.clear_state()
                snap_seg, gs_seg = client.run_tas_and_wait(header_cmd, committed_lines, committed_frames)
                if gs_seg is None:
                    print(f"  [Parada honesta] Falha ao carregar {nxt_rid} via checkpoint.")
                    break
                client.save_state()
                base_deaths = snap_seg.deaths
                seg_berry_base = snap_seg.berries
                checkpoint_resumes.append(f"{cur_rid}->{nxt_rid}")
                rooms_cleared.append(cur_rid)
                room_visit_counts[nxt_rid] = room_visit_counts.get(nxt_rid, 0) + 1
                continue

            print(f"  [Parada honesta] Nao foi possivel atravessar {cur_rid} -> {nxt_rid} continuamente.")
            break
        continuous_transitions += 1
        rooms_cleared.append(cur_rid)
        room_visit_counts[nxt_rid] = room_visit_counts.get(nxt_rid, 0) + 1

    # Re-sincroniza no último frame comprometido vivo para garantir snapshot sem morte residual
    client.clear_state()
    final_snap, final_gs = client.run_tas_and_wait(header_cmd, committed_lines, committed_frames)
    if final_gs and _canonical_room(str(final_gs.get("RoomName", ""))) == room_walk[-1]:
        rooms_cleared.append(room_walk[-1])

    total_frames_all = prior_frames + committed_frames
    total_live_berries = prior_berries + max(0, final_snap.berries - seg_berry_base)
    total_live_deaths = prior_deaths + max(0, final_snap.deaths - base_deaths)

    script_sections.append(f"# FIM DA ROTA LIVE: {chapter_key} | Quadros: {total_frames_all}")
    final_text = "\n".join(script_sections) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_text, encoding="utf-8")
    if install_path is not None and install_path.parent.exists():
        install_path.write_text(final_text, encoding="utf-8")

    ok_syntax, issues, _parsed_frames = validate_celestetas_script(final_text)
    summary = {
        "chapter": chapter_key,
        "alpha": alpha,
        "planned_walk_rooms": len(room_walk),
        "rooms_cleared_live": rooms_cleared,
        "continuous_transitions": continuous_transitions,
        "checkpoint_resumes": checkpoint_resumes,
        "total_frames": total_frames_all,
        "live_berries": total_live_berries,
        "live_deaths": total_live_deaths,
        "syntax_valid": ok_syntax,
        "syntax_issues": issues,
        "final_room": _canonical_room(str((final_gs or {}).get("RoomName", ""))),
        "out_path": out_path.as_posix(),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n=== Resumo Closed-Loop Live CelesteTAS ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sintetizador closed-loop StratGraph <-> Celeste ao vivo")
    parser.add_argument("--chapter", default="1_forsaken_city", help="Nome do dataset em datasets/celeste/")
    parser.add_argument("--alpha", type=float, default=0.05, help="Alpha do StratGraph (padrao: 0.05)")
    parser.add_argument(
        "--out",
        default="tas/celeste/1_forsaken_city_live.tas",
        help="Caminho de saida do arquivo .tas validado ao vivo",
    )
    parser.add_argument(
        "--report-json",
        default="results/live_celeste_ch1_validation.json",
        help="Caminho opcional para salvar o resumo JSON da validacao ao vivo",
    )
    parser.add_argument(
        "--install-to",
        default=r"D:\SteamLibrary\steamapps\common\Celeste\Celeste.tas",
        help="Copia adicional opcional na pasta do Celeste",
    )
    parser.add_argument("--max-rooms", type=int, default=None, help="Limite opcional de visitas de sala")
    parser.add_argument(
        "--no-room-checkpoints",
        dest="allow_room_checkpoints",
        action="store_false",
        default=True,
        help="Desabilita retomada via console load caso alguma sala exceda o limite continuo",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    area_id = CHAPTER_AREA_IDS.get(args.chapter, 1)
    solve_chapter_live(
        dataset_dir=Path("datasets/celeste") / args.chapter,
        alpha=args.alpha,
        out_path=Path(args.out),
        install_path=Path(args.install_to) if args.install_to else None,
        max_rooms=args.max_rooms,
        area_id=area_id,
        allow_room_checkpoints=args.allow_room_checkpoints,
        report_path=Path(args.report_json) if args.report_json else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
