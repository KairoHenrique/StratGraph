"""Simulador 60Hz fiel à cinemática subpixel de *Celeste* e planejador A* por macro-ações.

Constrói o mapa exato da sala a partir do JSON ao vivo do endpoint `/tas/game_state`
(Everest DebugRC + CelesteTAS) e de entidades opcionais do `.bin` (`refill`, `spring`,
`zipMover`), planejando sequências de quadros compatíveis com:
  - 1 dash único (`dashes = 1`, restaurado apenas no solo, mola ou cristal `refill`);
  - colisão AABB real (`8x11` em torno da base `(x, y)`), *jump-thrus*, espinhos e *spinners*;
  - escalada com estamina (`110.0`), pulos variáveis (`varJumpTime = 0.20s`), *coyote time*
    e *wall-jumps*.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
import math
from typing import Iterable

# Constantes de física de Celeste a 60 FPS (dt = 1/60 s)
DT = 1.0 / 60.0
MAX_RUN = 90.0
RUN_ACCEL = 1000.0
RUN_REDUCE = 400.0
AIR_MULT = 0.65
GRAVITY = 900.0
HALF_GRAV_THRESH = 40.0
MAX_FALL = 160.0
FAST_MAX_FALL = 240.0
JUMP_SPEED = -105.0
JUMP_H_BOOST = 40.0
VAR_JUMP_FRAMES = 12
COYOTE_FRAMES = 5
WALL_JUMP_HSPEED = 130.0
CLIMB_UP_SPEED = -45.0
CLIMB_DOWN_SPEED = 80.0
CLIMB_MAX_STAMINA = 110.0
DASH_SPEED = 240.0
END_DASH_SPEED = 160.0
DASH_FREEZE_FRAMES = 3
DASH_ATTACK_FRAMES = 10
SPRING_VY = -185.0


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def overlaps(self, ox: float, oy: float, ow: float, oh: float) -> bool:
        return (
            ox < self.x + self.w
            and ox + ow > self.x
            and oy < self.y + self.h
            and oy + oh > self.y
        )


@dataclass(slots=True)
class SimPlayer:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    on_ground: bool = True
    dashes: int = 1
    stamina: float = CLIMB_MAX_STAMINA
    var_jump_timer: int = 0
    var_jump_speed: float = 0.0
    coyote_timer: int = COYOTE_FRAMES
    dash_freeze: int = 0
    dash_timer: int = 0
    dash_dx: float = 0.0
    dash_dy: float = 0.0
    force_move_dir: int = 0
    force_move_timer: int = 0
    wall_slide_dir: int = 0
    dead: bool = False
    refill_cooldown: int = 0
    auto_jump: bool = False
    half_grav_dash: bool = False

    @classmethod
    def from_game_state(
        cls,
        gs: dict,
        dashes: int | None = None,
        stamina: float | None = None,
    ) -> "SimPlayer":
        """Constrói `SimPlayer` sincronizado com `/tas/game_state` ao vivo."""
        pl = gs["Player"]
        pos = pl["Position"]
        rem = pl.get("PositionRemainder", {"X": 0.0, "Y": 0.0})
        spd = pl["Speed"]
        og = bool(pl.get("OnGround", False))
        px = float(pos["X"]) + float(rem.get("X", 0.0))
        py = float(pos["Y"]) + float(rem.get("Y", 0.0))
        vx = float(spd["X"])
        vy = float(spd["Y"])
        if dashes is None:
            dashes = int(pl.get("Dashes", 1 if og else 1))
        if stamina is None:
            stamina = float(pl.get("Stamina", CLIMB_MAX_STAMINA if og else CLIMB_MAX_STAMINA))
        return cls(
            x=px,
            y=py,
            vx=vx,
            vy=vy,
            on_ground=og,
            dashes=dashes,
            stamina=stamina,
            coyote_timer=COYOTE_FRAMES if og else 0,
            dead=bool(pl.get("Dead", False)),
        )


def _approach(val: float, target: float, max_move: float) -> float:
    if val < target:
        return min(val + max_move, target)
    if val > target:
        return max(val - max_move, target)
    return target


class RoomModel60Hz:
    """Modelo geométrico e físico de uma sala única para busca A* a 60Hz."""

    def __init__(
        self,
        bx: int,
        by: int,
        bw: int,
        bh: int,
        solids: list[list[bool]],
        jump_thrus: list[Rect],
        spikes: list[tuple[Rect, int]],
        spinners: list[Rect],
        springs: list[Rect] | None = None,
        refills: list[Rect] | None = None,
    ) -> None:
        self.bx = bx
        self.by = by
        self.bw = bw
        self.bh = bh
        self.wt = max(1, bw // 8)
        self.ht = max(1, bh // 8)
        self.solids = solids
        self.jump_thrus = jump_thrus
        self.spikes = spikes
        self.spinners = spinners
        self.springs = springs or []
        self.refills = refills or []

    @classmethod
    def from_game_state(
        cls,
        gs: dict,
        room_entities: list[tuple[str, dict]] | None = None,
    ) -> "RoomModel60Hz":
        """Constrói o `RoomModel60Hz` a partir do JSON retornado por `/tas/game_state`."""
        bounds = gs["Level"]["Bounds"]
        bx, by, bw, bh = int(bounds["X"]), int(bounds["Y"]), int(bounds["W"]), int(bounds["H"])
        wt, ht = max(1, bw // 8), max(1, bh // 8)

        solids_lines = str(gs.get("SolidsData", "")).splitlines()
        solids: list[list[bool]] = [[False] * wt for _ in range(ht)]
        for r in range(min(ht, len(solids_lines))):
            line = solids_lines[r]
            for c in range(min(wt, len(line))):
                solids[r][c] = line[c] != "0"

        for st in gs.get("StaticSolids", []):
            sx, sy, sw, sh = int(st["X"]), int(st["Y"]), int(st["W"]), int(st["H"])
            c0 = max(0, (sx - bx) // 8)
            c1 = min(wt, math.ceil((sx + sw - bx) / 8.0))
            r0 = max(0, (sy - by) // 8)
            r1 = min(ht, math.ceil((sy + sh - by) / 8.0))
            for r in range(r0, r1):
                for c in range(c0, c1):
                    solids[r][c] = True

        jts = [
            Rect(
                float(jt["Bounds"]["X"]),
                float(jt["Bounds"]["Y"]),
                float(jt["Bounds"]["W"]),
                float(jt["Bounds"]["H"]),
            )
            for jt in gs.get("JumpThrus", [])
        ]

        spikes: list[tuple[Rect, int]] = []
        for sp in gs.get("Spikes", []):
            sb = sp["Bounds"]
            spikes.append(
                (Rect(float(sb["X"]), float(sb["Y"]), float(sb["W"]), float(sb["H"])), int(sp.get("Direction", 0)))
            )

        spinners: list[Rect] = []
        for sp in gs.get("Spinners", []):
            sb = sp.get("Bounds", sp)
            if "X" in sb:
                spinners.append(Rect(float(sb["X"]), float(sb["Y"]), float(sb.get("W", 12)), float(sb.get("H", 12))))

        springs: list[Rect] = []
        refills: list[Rect] = []
        if room_entities:
            for ename, attrs in room_entities:
                ex = bx + float(attrs.get("x", 0.0))
                ey = by + float(attrs.get("y", 0.0))
                if ename in ("spring", "wallSpringLeft", "wallSpringRight"):
                    springs.append(Rect(ex - 6, ey - 8, 12, 8))
                elif ename == "refill":
                    refills.append(Rect(ex - 6, ey - 6, 12, 12))

        return cls(bx, by, bw, bh, solids, jts, spikes, spinners, springs, refills)

    def solid_at_box(self, x: float, y: float, w: float = 8.0, h: float = 11.0) -> bool:
        """Retorna True se o retângulo `[x, x+w) x [y, y+h)` colide com algum bloco sólido."""
        c0 = int(math.floor((x - self.bx) / 8.0))
        c1 = int(math.floor((x + w - 0.001 - self.bx) / 8.0))
        r0 = int(math.floor((y - self.by) / 8.0))
        r1 = int(math.floor((y + h - 0.001 - self.by) / 8.0))
        for r in range(r0, r1 + 1):
            if r < 0:
                continue
            if r >= self.ht:
                continue
            for c in range(c0, c1 + 1):
                if c < 0 or c >= self.wt:
                    continue
                if self.solids[r][c]:
                    return True
        return False

    def player_collides_solid(self, px: float, py: float) -> bool:
        """Hitbox padrão 8x11 da Madeline com base centrada em `(px, py)`."""
        return self.solid_at_box(round(px) - 4.0, round(py) - 11.0, 8.0, 11.0)

    def on_ground(self, px: float, py: float, down_only: bool = True) -> bool:
        if self.solid_at_box(round(px) - 4.0, round(py), 8.0, 1.0):
            return True
        if down_only:
            rx, ry = round(px) - 4.0, round(py)
            for jt in self.jump_thrus:
                if rx + 8.0 > jt.x and rx < jt.x + jt.w and abs(ry - jt.y) <= 1.0:
                    return True
        return False

    def wall_next_to(self, px: float, py: float, direction: int, dist: float = 3.0) -> bool:
        rx = round(px) - 4.0 + (dist if direction > 0 else -dist)
        return self.solid_at_box(rx, round(py) - 11.0, 8.0, 10.0)

    def is_lethal(self, px: float, py: float, vx: float, vy: float) -> bool:
        # Caiu abaixo do fundo da sala -> morte (exceto se saiu intencionalmente pela borda se aberta)
        if py > self.by + self.bh + 10.0:
            # Só é seguro se existir abertura no piso na coluna atual
            col = max(0, min(self.wt - 1, int((px - self.bx) // 8)))
            if self.solids[self.ht - 1][col]:
                return True
            if py > self.by + self.bh + 24.0:
                return True

        # Hurtbox 8x11 alcançando até a base (round(py)+1) para detectar espinhos sob os pés
        hx, hy, hw, hh = round(px) - 4.0, round(py) - 10.0, 8.0, 11.0
        for sp, direction in self.spikes:
            if sp.overlaps(hx, hy, hw, hh):
                # Em Celeste: spikesUp (0) mata se vy >= 0; spikesDown (1) se vy <= 0; L/R (2/3) sempre perigoso
                if direction == 0 and vy < -10.0:
                    continue
                if direction == 1 and vy > 10.0:
                    continue
                return True
        for sn in self.spinners:
            if sn.overlaps(hx, hy, hw, hh):
                return True
        return False

    def bfs_distance_field(
        self,
        targets_xy: list[tuple[float, float]],
    ) -> list[list[int]]:
        """Campo de distância geodésica em tiles 8x8 evitando paredes e espinhos."""
        inf = 10**6
        dist = [[inf] * self.wt for _ in range(self.ht)]
        dq: deque[tuple[int, int]] = deque()

        for tx, ty in targets_xy:
            tr = max(0, min(self.ht - 1, int((ty - 4.0 - self.by) // 8)))
            tc = max(0, min(self.wt - 1, int((tx - self.bx) // 8)))
            # Encontrar tile aberto mais próximo caso alvo esteja em borda sólida
            best = (tr, tc)
            if self.solids[tr][tc]:
                best_d = 999
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        rr, cc = tr + dr, tc + dc
                        if 0 <= rr < self.ht and 0 <= cc < self.wt and not self.solids[rr][cc]:
                            if abs(dr) + abs(dc) < best_d:
                                best_d = abs(dr) + abs(dc)
                                best = (rr, cc)
            r0, c0 = best
            if dist[r0][c0] > 0:
                dist[r0][c0] = 0
                dq.append((r0, c0))

        while dq:
            r, c = dq.popleft()
            d = dist[r][c] + 1
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.ht and 0 <= nc < self.wt and not self.solids[nr][nc]:
                    if d < dist[nr][nc]:
                        dist[nr][nc] = d
                        dq.append((nr, nc))
        return dist

    def heuristic_dist(self, px: float, py: float, field: list[list[int]], target_xy: tuple[float, float]) -> float:
        r = max(0, min(self.ht - 1, int((py - 4.0 - self.by) // 8)))
        c = max(0, min(self.wt - 1, int((px - self.bx) // 8)))
        gd = field[r][c]
        eucl = math.hypot(px - target_xy[0], py - target_xy[1])
        if gd >= 10**5:
            return eucl + 200.0
        return gd * 8.0 + 0.15 * eucl

    def extract_bfs_waypoints(
        self,
        start_xy: tuple[float, float],
        field: list[list[int]],
        step_tiles: int = 9,
    ) -> list[tuple[float, float]]:
        """Extrai checkpoints intermediários ao longo do menor caminho geodésico BFS."""
        r = max(0, min(self.ht - 1, int((start_xy[1] - 4.0 - self.by) // 8)))
        c = max(0, min(self.wt - 1, int((start_xy[0] - self.bx) // 8)))
        if field[r][c] >= 10**5:
            return []
        chain: list[tuple[int, int]] = [(r, c)]
        seen = {(r, c)}
        while field[r][c] > 0:
            best_n = None
            best_d = field[r][c]
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.ht and 0 <= nc < self.wt and (nr, nc) not in seen:
                    if field[nr][nc] < best_d:
                        best_d = field[nr][nc]
                        best_n = (nr, nc)
            if best_n is None:
                break
            r, c = best_n
            seen.add((r, c))
            chain.append((r, c))

        waypoints: list[tuple[float, float]] = []
        for idx in range(step_tiles, len(chain) - 3, step_tiles):
            wr, wc = chain[idx]
            waypoints.append((self.bx + wc * 8.0 + 4.0, self.by + wr * 8.0 + 8.0))
        return waypoints


def compute_doorway_targets(
    cur_bounds: tuple[int, int, int, int],
    next_bounds: tuple[int, int, int, int],
    room: RoomModel60Hz,
) -> list[Rect]:
    """Calcula retângulos abertos na fronteira compartilhada entre `cur_bounds` e `next_bounds`."""
    bx, by, bw, bh = cur_bounds
    nx, ny, nw, nh = next_bounds
    targets: list[Rect] = []

    def _spans(open_flags: list[bool]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        s = None
        for i, flag in enumerate(open_flags):
            if flag and s is None:
                s = i
            elif not flag and s is not None:
                out.append((s, i))
                s = None
        if s is not None:
            out.append((s, len(open_flags)))
        return out

    # Saída à direita
    if abs(nx - (bx + bw)) <= 8:
        y0 = max(by, ny)
        y1 = min(by + bh, ny + nh)
        r0 = max(0, (y0 - by) // 8)
        r1 = min(room.ht, (y1 - by) // 8)
        c = room.wt - 1
        flags = [not room.solids[r][c] for r in range(r0, r1)]
        for sr0, sr1 in _spans(flags):
            py0 = by + (r0 + sr0) * 8.0
            ph = max(8.0, (sr1 - sr0) * 8.0)
            targets.append(Rect(bx + bw - 2.0, py0, 14.0, ph))

    # Saída à esquerda
    if abs((nx + nw) - bx) <= 8:
        y0 = max(by, ny)
        y1 = min(by + bh, ny + nh)
        r0 = max(0, (y0 - by) // 8)
        r1 = min(room.ht, (y1 - by) // 8)
        c = 0
        flags = [not room.solids[r][c] for r in range(r0, r1)]
        for sr0, sr1 in _spans(flags):
            py0 = by + (r0 + sr0) * 8.0
            ph = max(8.0, (sr1 - sr0) * 8.0)
            targets.append(Rect(bx - 12.0, py0, 14.0, ph))

    # Saída por cima
    if abs((ny + nh) - by) <= 8:
        x0 = max(bx, nx)
        x1 = min(bx + bw, nx + nw)
        c0 = max(0, (x0 - bx) // 8)
        c1 = min(room.wt, (x1 - bx) // 8)
        r = 0
        flags = [not room.solids[r][c] for c in range(c0, c1)]
        for sc0, sc1 in _spans(flags):
            px0 = bx + (c0 + sc0) * 8.0
            pw = max(8.0, (sc1 - sc0) * 8.0)
            targets.append(Rect(px0, by - 12.0, pw, 16.0))

    # Saída por baixo
    if abs(ny - (by + bh)) <= 8:
        x0 = max(bx, nx)
        x1 = min(bx + bw, nx + nw)
        c0 = max(0, (x0 - bx) // 8)
        c1 = min(room.wt, (x1 - bx) // 8)
        r = room.ht - 1
        flags = [not room.solids[r][c] for c in range(c0, c1)]
        for sc0, sc1 in _spans(flags):
            px0 = bx + (c0 + sc0) * 8.0
            pw = max(8.0, (sc1 - sc0) * 8.0)
            targets.append(Rect(px0, by + bh - 4.0, pw, 16.0))

    # Fallback geométrico pelo centro da interseção caso a borda tenha blocos quebráveis
    if not targets:
        cx = max(bx, nx) + (min(bx + bw, nx + nw) - max(bx, nx)) * 0.5
        cy = max(by, ny) + (min(by + bh, ny + nh) - max(by, ny)) * 0.5
        targets.append(Rect(cx - 12.0, cy - 12.0, 24.0, 24.0))
    return targets


def step_celeste_60hz(
    room: RoomModel60Hz,
    p: SimPlayer,
    tokens: tuple[str, ...],
    prev_jump: bool,
    prev_dash: bool,
) -> tuple[SimPlayer, bool, bool]:
    """Avança 1 quadro (1/60s) na simulação física da Madeline."""
    if p.dead:
        return p, False, False

    np = SimPlayer(
        x=p.x,
        y=p.y,
        vx=p.vx,
        vy=p.vy,
        on_ground=p.on_ground,
        dashes=p.dashes,
        stamina=p.stamina,
        var_jump_timer=p.var_jump_timer,
        var_jump_speed=p.var_jump_speed,
        coyote_timer=p.coyote_timer,
        dash_freeze=p.dash_freeze,
        dash_timer=p.dash_timer,
        dash_dx=p.dash_dx,
        dash_dy=p.dash_dy,
        force_move_dir=p.force_move_dir,
        force_move_timer=p.force_move_timer,
        dead=False,
        refill_cooldown=max(0, p.refill_cooldown - 1),
        auto_jump=p.auto_jump,
        half_grav_dash=p.half_grav_dash,
    )

    move_x = (1 if "R" in tokens else 0) - (1 if "L" in tokens else 0)
    move_y = (1 if "D" in tokens else 0) - (1 if "U" in tokens else 0)
    jump_held = "J" in tokens
    dash_held = "X" in tokens
    grab_held = "G" in tokens
    jump_pressed = jump_held and not prev_jump
    dash_pressed = dash_held and not prev_dash

    if np.force_move_timer > 0:
        np.force_move_timer -= 1
        move_x = np.force_move_dir

    # Freeze frames do dash
    if np.dash_freeze > 0:
        np.dash_freeze -= 1
        return np, jump_held, dash_held

    # Interação com refills & springs
    hx, hy, hw, hh = round(np.x) - 4.0, round(np.y) - 11.0, 8.0, 11.0
    if np.refill_cooldown == 0:
        for rf in room.refills:
            if rf.overlaps(hx, hy, hw, hh) and np.dashes < 1:
                np.dashes = 1
                np.stamina = CLIMB_MAX_STAMINA
                np.refill_cooldown = 150
                break
    for sp in room.springs:
        if sp.overlaps(hx, hy, hw, hh):
            np.vy = SPRING_VY
            np.vx *= 0.7
            np.dashes = 1
            np.stamina = CLIMB_MAX_STAMINA
            np.dash_timer = 0
            np.var_jump_timer = VAR_JUMP_FRAMES
            np.var_jump_speed = SPRING_VY
            np.auto_jump = True
            np.on_ground = False

    # Iniciar o 1 dash único apenas se dashes >= 1
    if dash_pressed and np.dashes >= 1:
        np.dashes -= 1
        dx, dy = float(move_x), float(move_y)
        if dx == 0.0 and dy == 0.0:
            dx = 1.0
        mag = math.hypot(dx, dy)
        np.dash_dx = dx / mag
        np.dash_dy = dy / mag
        np.vx = np.dash_dx * DASH_SPEED
        np.vy = np.dash_dy * DASH_SPEED
        np.dash_freeze = DASH_FREEZE_FRAMES
        np.dash_timer = DASH_ATTACK_FRAMES + 1
        np.var_jump_timer = 0
        np.on_ground = False
        return np, jump_held, dash_held

    grounded = room.on_ground(np.x, np.y, down_only=not ("D" in tokens))
    np.on_ground = grounded
    if grounded:
        np.coyote_timer = COYOTE_FRAMES
        np.stamina = CLIMB_MAX_STAMINA
        np.half_grav_dash = False
        if np.dash_timer == 0:
            np.dashes = 1
    elif np.coyote_timer > 0:
        np.coyote_timer -= 1

    # Estado ativo de dash (10 quadros a 240 px/s, depois EndDash no 11º quadro antes da física normal)
    if np.dash_timer > 0:
        np.dash_timer -= 1
        if np.dash_timer > 0:
            np.vx = np.dash_dx * DASH_SPEED
            np.vy = np.dash_dy * DASH_SPEED
        else:
            if np.dash_dy <= 0.0:
                np.vx = np.dash_dx * END_DASH_SPEED
                np.vy = np.dash_dy * (END_DASH_SPEED * 0.75)
                if np.dash_dy < 0.0:
                    np.half_grav_dash = True
    else:
        # Escalada com G junto à parede
        climbing = False
        if grab_held and np.stamina > 0.0:
            wall_r = room.wall_next_to(np.x, np.y, 1, 2.0)
            wall_l = room.wall_next_to(np.x, np.y, -1, 2.0)
            if (move_x >= 0 and wall_r) or (move_x <= 0 and wall_l):
                climbing = True
                np.vx = 0.0
                climb_dir = 1 if (wall_r and move_x >= 0) else -1
                wall_waist = room.solid_at_box(round(np.x) - 4.0 + climb_dir * 2.0, round(np.y) - 6.0, 8.0, 1.0)
                if move_y < 0:
                    if wall_waist:
                        np.vy = _approach(np.vy, CLIMB_UP_SPEED, 900.0 * DT)
                        np.stamina = max(0.0, np.stamina - 45.45 * DT)
                    else:
                        np.vy = _approach(np.vy, 0.0, 900.0 * DT)
                        np.stamina = max(0.0, np.stamina - 10.0 * DT)
                elif move_y > 0:
                    np.vy = _approach(np.vy, CLIMB_DOWN_SPEED, 900.0 * DT)
                else:
                    np.vy = _approach(np.vy, 0.0, 900.0 * DT)
                    np.stamina = max(0.0, np.stamina - 10.0 * DT)
                if jump_pressed and move_x == 0:
                    np.vy = JUMP_SPEED
                    np.var_jump_timer = VAR_JUMP_FRAMES
                    np.var_jump_speed = JUMP_SPEED
                    np.stamina = max(0.0, np.stamina - 27.5)
                    climbing = False

        if not climbing:
            # Movimento horizontal
            mult = 1.0 if grounded else AIR_MULT
            target_vx = move_x * MAX_RUN
            if abs(np.vx) > MAX_RUN and math.copysign(1.0, np.vx) == move_x and move_x != 0:
                np.vx = _approach(np.vx, target_vx, RUN_REDUCE * mult * DT)
            else:
                accel = RUN_ACCEL if move_x != 0 else RUN_REDUCE
                np.vx = _approach(np.vx, target_vx, accel * mult * DT)

            # Gravidade vertical
            if not grounded:
                mf = FAST_MAX_FALL if move_y > 0 else MAX_FALL
                use_half = abs(np.vy) < HALF_GRAV_THRESH and (jump_held or np.auto_jump or np.half_grav_dash)
                grav = GRAVITY * (0.5 if use_half else 1.0)
                np.vy = _approach(np.vy, mf, grav * DT)
                if np.vy >= HALF_GRAV_THRESH:
                    np.half_grav_dash = False

            # Pulo no chão / coyote ou walljump
            if jump_pressed:
                if np.coyote_timer > 0:
                    np.vy = JUMP_SPEED
                    np.vx += move_x * JUMP_H_BOOST
                    np.var_jump_timer = VAR_JUMP_FRAMES
                    np.var_jump_speed = JUMP_SPEED
                    np.coyote_timer = 0
                    np.on_ground = False
                elif room.wall_next_to(np.x, np.y, -1, 3.0):
                    np.vx = WALL_JUMP_HSPEED
                    np.vy = JUMP_SPEED
                    np.var_jump_timer = VAR_JUMP_FRAMES
                    np.var_jump_speed = JUMP_SPEED
                    np.force_move_dir = 1 if move_x >= 0 else 0
                    np.force_move_timer = 9 if move_x >= 0 else 0
                elif room.wall_next_to(np.x, np.y, 1, 3.0):
                    np.vx = -WALL_JUMP_HSPEED
                    np.vy = JUMP_SPEED
                    np.var_jump_timer = VAR_JUMP_FRAMES
                    np.var_jump_speed = JUMP_SPEED
                    np.force_move_dir = -1 if move_x <= 0 else 0
                    np.force_move_timer = 9 if move_x <= 0 else 0

        if np.var_jump_timer > 0:
            if jump_held or np.auto_jump:
                np.vy = min(np.vy, np.var_jump_speed)
                np.var_jump_timer -= 1
            else:
                np.var_jump_timer = 0
                np.auto_jump = False
        else:
            np.auto_jump = False

    # Integração pixel a pixel (eixo X depois eixo Y) respeitando sólidos & jumpThrus
    dx_total = np.vx * DT
    dy_total = np.vy * DT

    steps_x = max(1, int(math.ceil(abs(dx_total))))
    step_dx = dx_total / steps_x
    for _ in range(steps_x):
        nx = np.x + step_dx
        if not room.player_collides_solid(nx, np.y):
            np.x = nx
        else:
            np.vx = 0.0
            break

    steps_y = max(1, int(math.ceil(abs(dy_total))))
    step_dy = dy_total / steps_y
    for _ in range(steps_y):
        ny = np.y + step_dy
        blocked = room.player_collides_solid(np.x, ny)
        if not blocked and step_dy > 0.0 and not ("D" in tokens):
            # Colisão com topo de JumpThru
            rx = round(np.x) - 4.0
            prev_ry = round(np.y)
            next_ry = round(ny)
            if next_ry > prev_ry:
                for jt in room.jump_thrus:
                    if rx + 8.0 > jt.x and rx < jt.x + jt.w and prev_ry <= jt.y < next_ry:
                        ny = jt.y
                        blocked = True
                        break
        if not blocked:
            np.y = ny
        else:
            np.vy = 0.0
            break

    np.on_ground = room.on_ground(np.x, np.y, down_only=not ("D" in tokens))
    if room.is_lethal(np.x, np.y, np.vx, np.vy):
        np.dead = True

    return np, jump_held, dash_held


def _roll_macro(
    room: RoomModel60Hz,
    start: SimPlayer,
    segments: Iterable[tuple[int, tuple[str, ...]]],
    prev_jump: bool,
    prev_dash: bool,
    goal_rects: list[Rect],
) -> tuple[SimPlayer, list[tuple[int, tuple[str, ...]]], bool, bool, bool]:
    """Executa uma macro-sequência no modelo 60Hz, parando cedo se atingir qualquer alvo."""
    cur = start
    pj, pd = prev_jump, prev_dash
    executed: list[tuple[int, tuple[str, ...]]] = []
    reached = False

    for n_fr, toks in segments:
        done_fr = 0
        for _ in range(n_fr):
            cur, pj, pd = step_celeste_60hz(room, cur, toks, pj, pd)
            done_fr += 1
            if cur.dead:
                return cur, executed, pj, pd, False
            hx, hy = cur.x - 4.0, cur.y - 11.0
            if any(g.overlaps(hx, hy, 8.0, 11.0) for g in goal_rects):
                reached = True
                break
        if done_fr > 0:
            if executed and executed[-1][1] == toks:
                executed[-1] = (executed[-1][0] + done_fr, toks)
            else:
                executed.append((done_fr, toks))
        if reached:
            break

    return cur, executed, pj, pd, reached


def _candidate_macros(
    room: RoomModel60Hz,
    p: SimPlayer,
    prefer_dx: float,
    prefer_dy: float,
    forbid_dash: bool = False,
) -> list[list[tuple[int, tuple[str, ...]]]]:
    """Gera macro-ações fisicamente válidas de acordo com o estado atual."""
    macros: list[list[tuple[int, tuple[str, ...]]]] = []
    dirs = ("R", "L") if prefer_dx >= 0 else ("L", "R")

    if p.on_ground or p.coyote_timer > 0:
        for d in dirs:
            macros.append([(4, (d,))])
            macros.append([(10, (d,))])
            macros.append([(4, (d, "J")), (6, (d,))])
            macros.append([(10, (d, "J")), (6, (d,))])
            macros.append([(15, (d, "J")), (6, (d,))])
            macros.append([(12, (d, "J")), (8, (d, "U", "G"))])
            macros.append([(6, (d, "D"))])
        macros.append([(14, ("J",))])
        macros.append([(5, ("D",))])
        macros.append([(6, ())])
    else:
        for d in dirs:
            macros.append([(8, (d,))])
            macros.append([(8, (d, "J"))])
        macros.append([(8, ())])

    # Escalada contínua / salto de borda / troca de parede em chaminé
    if p.stamina > 12.0:
        if room.wall_next_to(p.x, p.y, 1, 3.0):
            macros.append([(14, ("R", "U", "G"))])
            macros.append([(8, ("R", "U", "G")), (8, ("R", "J")), (6, ("R",))])
            macros.append([(10, ("L", "J")), (8, ("L", "U", "G"))])
            macros.append([(12, ("L", "J")), (6, ("L",))])
            macros.append([(10, ("R", "D", "G"))])
        if room.wall_next_to(p.x, p.y, -1, 3.0):
            macros.append([(14, ("L", "U", "G"))])
            macros.append([(8, ("L", "U", "G")), (8, ("L", "J")), (6, ("L",))])
            macros.append([(10, ("R", "J")), (8, ("R", "U", "G"))])
            macros.append([(12, ("R", "J")), (6, ("R",))])
            macros.append([(10, ("L", "D", "G"))])

    # 1 Dash único (SOMENTE se dashes >= 1 e não proibido por morango alado)
    if p.dashes >= 1 and not forbid_dash:
        dash_dirs: list[tuple[str, ...]] = [
            ("R", "U"),
            ("L", "U"),
            ("U",),
            ("R",),
            ("L",),
            ("R", "D"),
            ("L", "D"),
        ]

        def _dir_score(dt: tuple[str, ...]) -> float:
            vx = 1.0 if "R" in dt else (-1.0 if "L" in dt else 0.0)
            vy = -1.0 if "U" in dt else (1.0 if "D" in dt else 0.0)
            return -(vx * prefer_dx + vy * prefer_dy)

        dash_dirs.sort(key=_dir_score)
        for dtoks in dash_dirs[:5]:
            lr = tuple(t for t in dtoks if t in ("L", "R"))
            macros.append([(1, (*dtoks, "X")), (13, dtoks), (6, lr)])
            if "L" in dtoks or "R" in dtoks:
                macros.append([(1, (*dtoks, "X")), (13, dtoks), (8, (*lr, "U", "G"))])

    return macros


def plan_to_goal_60hz(
    room: RoomModel60Hz,
    start: SimPlayer,
    goal_rect: Rect | list[Rect],
    max_expansions: int = 3200,
    max_frames: int = 460,
    diverse_count: int = 3,
    forbid_dash: bool = False,
) -> list[list[tuple[int, tuple[str, ...]]]]:
    """Busca A* no modelo 60Hz retornando até `diverse_count` planos macro viáveis."""
    goal_rects = [goal_rect] if isinstance(goal_rect, Rect) else list(goal_rect)
    if not goal_rects:
        return []

    centers = [(g.x + g.w * 0.5, g.y + g.h * 0.5) for g in goal_rects]
    field = room.bfs_distance_field(centers)

    def _nearest_center(px: float, py: float) -> tuple[float, float]:
        return min(centers, key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)

    counter = 0
    c0 = _nearest_center(start.x, start.y)
    h0 = room.heuristic_dist(start.x, start.y, field, c0)
    heap: list[tuple[float, int, int, SimPlayer, bool, bool, list[tuple[int, tuple[str, ...]]]]] = [
        (h0, 0, counter, start, False, False, [])
    ]
    visited: dict[tuple[int, int, int, bool, int, int], int] = {}
    solutions: list[list[tuple[int, tuple[str, ...]]]] = []
    best_fallback: tuple[float, list[tuple[int, tuple[str, ...]]]] = (h0, [])

    expansions = 0
    while heap and expansions < max_expansions:
        f_score, elapsed_fr, _, cur, pj, pd, ops = heapq.heappop(heap)
        expansions += 1

        nc = _nearest_center(cur.x, cur.y)
        if ops:
            cur_h = room.heuristic_dist(cur.x, cur.y, field, nc)
            if cur_h < best_fallback[0]:
                best_fallback = (cur_h, ops)

        if elapsed_fr >= max_frames:
            continue

        state_key = (
            int(cur.x // 4),
            int(cur.y // 4),
            cur.dashes,
            cur.on_ground,
            int(cur.vy // 40),
            int(cur.stamina // 40),
        )
        prev_best = visited.get(state_key)
        if prev_best is not None and prev_best <= elapsed_fr:
            continue
        visited[state_key] = elapsed_fr

        for macro in _candidate_macros(room, cur, nc[0] - cur.x, nc[1] - cur.y, forbid_dash=forbid_dash):
            nxt, used_ops, npj, npd, hit = _roll_macro(room, cur, macro, pj, pd, goal_rects)
            if nxt.dead or not used_ops:
                continue
            added_fr = sum(n for n, _ in used_ops)
            new_fr = elapsed_fr + added_fr
            merged_ops = _merge_ops(ops, used_ops)

            if hit:
                solutions.append(merged_ops)
                if len(solutions) >= diverse_count:
                    return solutions
                continue

            if new_fr <= max_frames:
                nc_nxt = _nearest_center(nxt.x, nxt.y)
                nh = room.heuristic_dist(nxt.x, nxt.y, field, nc_nxt)
                counter += 1
                heapq.heappush(heap, (new_fr * 0.45 + nh, new_fr, counter, nxt, npj, npd, merged_ops))

    if solutions:
        return solutions
    return [best_fallback[1]] if best_fallback[1] else []


_TOKEN_ORDER = {"L": 0, "R": 1, "U": 2, "D": 3, "J": 4, "K": 5, "X": 6, "G": 7}


def _merge_ops(
    a: list[tuple[int, tuple[str, ...]]],
    b: list[tuple[int, tuple[str, ...]]],
) -> list[tuple[int, tuple[str, ...]]]:
    out = list(a)
    for n, toks in b:
        toks_sorted = tuple(sorted(set(toks), key=lambda t: _TOKEN_ORDER.get(t, 99)))
        if out and out[-1][1] == toks_sorted:
            out[-1] = (out[-1][0] + n, toks_sorted)
        else:
            out.append((n, toks_sorted))
    return out
