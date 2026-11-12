using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using Celeste;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Input;
using Monocle;

namespace Celeste.Mod.StratGraph
{
    /// <summary>
    /// Entidade HUD e Executor TAS in-game para Celeste que lê as rotas e waypoints físicos
    /// exportados pelo StratGraph (`stratgraph_routes.json`) e:
    ///   1. Desenha na tela os dados da sala atual, camada (`L0`/`L1`) e becos contraídos;
    ///   2. Desenha a linha de trajetória física TAS (waypoints 8x8) diretamente sobre a sala;
    ///   3. Ao pressionar `F5`, ativa/desativa o Modo Bot TAS, movimentando o player
    ///      automaticamente ao longo dos waypoints físicos calculados pelo StratGraph.
    ///
    /// Autoria:
    ///   - Heitor Henrique Zonho
    ///   - Kairo Henrique Ferreira Martins
    ///   - Michel Pires da Silva
    /// </summary>
    public class StratGraphHudEntity : Entity
    {
        private readonly Dictionary<int, string> _areaToSlug = new Dictionary<int, string>
        {
            { 1, "1_forsaken_city" },
            { 2, "2_old_site" },
            { 3, "3_celestial_resort" },
            { 4, "4_golden_ridge" },
            { 5, "5_mirror_temple" },
            { 6, "6_reflection" },
            { 7, "7_summit" },
            { 9, "9_core" }
        };

        private readonly Dictionary<string, List<string>> _stratRouteByChapter =
            new Dictionary<string, List<string>>();

        private readonly Dictionary<string, List<Vector2>> _tasWaypointsByChapter =
            new Dictionary<string, List<Vector2>>();

        private readonly Dictionary<string, List<Vector2>> _bfsWaypointsByChapter =
            new Dictionary<string, List<Vector2>>();

        private readonly Dictionary<string, string> _weaponRoomByChapter =
            new Dictionary<string, string>();

        private readonly Dictionary<string, Dictionary<string, string>> _contractedByChapter =
            new Dictionary<string, Dictionary<string, string>>();

        private readonly Dictionary<string, string> _summaryByChapter =
            new Dictionary<string, string>();

        private static StratGraphHudEntity _activeInstance;

        private bool _armedLayerActive;
        private bool _tasBotActive;
        private bool _useBfsRoute;
        private int _currentWaypointIndex;
        private string _lastChapterSlug = "";
        private float _dashCooldown;
        private float _jumpCooldown;
        private float _holdJumpTimer;
        private bool _holdGrab;
        private int _lastWaypointRoomCount;
        private string _lastRoomName = "";

        public StratGraphHudEntity(string routesJsonPath)
        {
            Tag = Tags.HUD | Tags.Global | Tags.PauseUpdate | Tags.TransitionUpdate;
            Depth = -100000;
            _activeInstance = this;
            LoadRoutesJson(routesJsonPath);
        }

        public static void BeforePlayerUpdate(Player player)
        {
            if (_activeInstance != null && player != null)
            {
                _activeInstance.DrivePlayerInputs(player);
            }
        }

        public static bool FilterButtonCheck(bool orig, VirtualButton btn)
        {
            if (_activeInstance != null && _activeInstance._tasBotActive && btn == global::Celeste.Input.Jump)
            {
                if (_activeInstance._holdJumpTimer > 0f)
                {
                    return true;
                }
            }
            return orig;
        }

        public static bool FilterGrabCheck(bool orig)
        {
            if (_activeInstance != null && _activeInstance._tasBotActive && _activeInstance._holdGrab)
            {
                return true;
            }
            return orig;
        }

        private static string ExtractJsonObjectBlock(string raw, string key)
        {
            int idx = raw.IndexOf(key, StringComparison.Ordinal);
            if (idx < 0)
            {
                return "";
            }
            int openBrace = raw.IndexOf('{', idx);
            if (openBrace < 0)
            {
                return "";
            }
            int depth = 0;
            bool inStr = false;
            bool escaped = false;
            for (int i = openBrace; i < raw.Length; i++)
            {
                char ch = raw[i];
                if (escaped)
                {
                    escaped = false;
                    continue;
                }
                if (ch == '\\' && inStr)
                {
                    escaped = true;
                    continue;
                }
                if (ch == '"')
                {
                    inStr = !inStr;
                    continue;
                }
                if (!inStr)
                {
                    if (ch == '{') depth++;
                    else if (ch == '}')
                    {
                        depth--;
                        if (depth == 0)
                        {
                            return raw.Substring(openBrace, i - openBrace + 1);
                        }
                    }
                }
            }
            return raw.Substring(openBrace);
        }

        public static void AttachToLevel(Level level)
        {
            if (level == null)
            {
                return;
            }
            try
            {
                if (Engine.Instance != null && Engine.Instance.Window != null)
                {
                    Engine.Instance.Window.Title = "Celeste — [StratGraph TAS Mod Ativo | F5: Bot TAS | F6: Rota]";
                }
            }
            catch
            {
            }
            string baseDir = AppDomain.CurrentDomain.BaseDirectory ?? ".";
            string jsonPath = Path.Combine(baseDir, "stratgraph_routes.json");
            level.Add(new StratGraphHudEntity(jsonPath));
        }

        private void LoadRoutesJson(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
            {
                return;
            }

            string raw = File.ReadAllText(path);
            foreach (KeyValuePair<int, string> kv in _areaToSlug)
            {
                string slug = kv.Value;
                string key = "\"celeste_" + slug + "\"";
                string block = ExtractJsonObjectBlock(raw, key);
                if (string.IsNullOrEmpty(block))
                {
                    continue;
                }

                Match wMatch = Regex.Match(block, "\"weapon_room\"\\s*:\\s*\"([^\"]+)\"");
                if (wMatch.Success)
                {
                    _weaponRoomByChapter[slug] = wMatch.Groups[1].Value;
                }

                Match sumMatch = Regex.Match(block, "\"hud_summary\"\\s*:\\s*\"([^\"]+)\"");
                if (sumMatch.Success)
                {
                    _summaryByChapter[slug] = sumMatch.Groups[1].Value;
                }

                Match routeMatch = Regex.Match(block, "\"strat_rooms\"\\s*:\\s*\\[([^\\]]+)\\]");
                if (routeMatch.Success)
                {
                    List<string> rooms = new List<string>();
                    MatchCollection items = Regex.Matches(routeMatch.Groups[1].Value, "\"([^\"]+)\"");
                    foreach (Match m in items)
                    {
                        rooms.Add(m.Groups[1].Value);
                    }
                    _stratRouteByChapter[slug] = rooms;
                }

                Match contractedMatch = Regex.Match(block, "\"contracted_text\"\\s*:\\s*\"([^\"]*)\"");
                if (contractedMatch.Success)
                {
                    Dictionary<string, string> map = new Dictionary<string, string>();
                    string[] pairs = contractedMatch.Groups[1].Value.Split(';');
                    foreach (string p in pairs)
                    {
                        string[] kvp = p.Split(':');
                        if (kvp.Length == 2)
                        {
                            map[kvp[0].Trim()] = kvp[1].Trim();
                        }
                    }
                    _contractedByChapter[slug] = map;
                }

                Match wptsMatch = Regex.Match(block, "\"tas_waypoints_flat\"\\s*:\\s*\"([^\"]*)\"");
                if (wptsMatch.Success)
                {
                    _tasWaypointsByChapter[slug] = ParseWaypointsString(wptsMatch.Groups[1].Value);
                }

                Match bfsWptsMatch = Regex.Match(block, "\"bfs_waypoints_flat\"\\s*:\\s*\"([^\"]*)\"");
                if (bfsWptsMatch.Success)
                {
                    _bfsWaypointsByChapter[slug] = ParseWaypointsString(bfsWptsMatch.Groups[1].Value);
                }
            }
        }

        private List<Vector2> ParseWaypointsString(string rawPts)
        {
            List<Vector2> pts = new List<Vector2>();
            string[] pairs = rawPts.Split(';');
            foreach (string p in pairs)
            {
                string[] xy = p.Split(',');
                if (xy.Length == 2)
                {
                    float wx, wy;
                    if (float.TryParse(xy[0], NumberStyles.Float, CultureInfo.InvariantCulture, out wx) &&
                        float.TryParse(xy[1], NumberStyles.Float, CultureInfo.InvariantCulture, out wy))
                    {
                        pts.Add(new Vector2(wx, wy));
                    }
                }
            }
            return pts;
        }

        public override void Update()
        {
            base.Update();
            _activeInstance = this;

            if (MInput.Keyboard != null && MInput.Keyboard.Pressed(Keys.F5))
            {
                _tasBotActive = !_tasBotActive;
                _currentWaypointIndex = -1;
                _holdJumpTimer = 0f;
                _holdGrab = false;
                if (!_tasBotActive && Scene is Level)
                {
                    Player pl = (Scene as Level).Tracker.GetEntity<Player>();
                    if (pl != null)
                    {
                        pl.OverrideDashDirection = null;
                    }
                }
            }
            if (MInput.Keyboard != null && MInput.Keyboard.Pressed(Keys.F6))
            {
                _useBfsRoute = !_useBfsRoute;
                _currentWaypointIndex = -1;
                _holdJumpTimer = 0f;
                _holdGrab = false;
            }

            Level level = Scene as Level;
            if (level == null || level.Session == null)
            {
                return;
            }

            int areaId = level.Session.Area.ID;
            string slug;
            if (!_areaToSlug.TryGetValue(areaId, out slug))
            {
                return;
            }

            if (_lastChapterSlug != slug)
            {
                _lastChapterSlug = slug;
                _armedLayerActive = false;
                _currentWaypointIndex = -1;
            }
        }

        private void DrivePlayerInputs(Player player)
        {
            if (player == null)
            {
                return;
            }
            if (player.Dead)
            {
                // Respeita morte real e reinicia no waypoint mais próximo após o respawn
                _currentWaypointIndex = -1;
                _holdJumpTimer = 0f;
                _holdGrab = false;
                return;
            }
            if (!_tasBotActive)
            {
                _holdJumpTimer = 0f;
                _holdGrab = false;
                return;
            }

            Level level = player.Scene as Level;
            if (level == null || level.Session == null || level.Transitioning)
            {
                return;
            }

            int areaId = level.Session.Area.ID;
            string slug;
            if (!_areaToSlug.TryGetValue(areaId, out slug))
            {
                return;
            }

            string curRoom = level.Session.Level ?? "";
            if (_lastRoomName != curRoom)
            {
                _lastRoomName = curRoom;
                _currentWaypointIndex = -1;
            }

            Dictionary<string, List<Vector2>> activeDict = _useBfsRoute
                ? _bfsWaypointsByChapter
                : _tasWaypointsByChapter;

            List<Vector2> waypoints;
            if (!activeDict.TryGetValue(slug, out waypoints) || waypoints.Count == 0)
            {
                return;
            }

            // Regras 100% reais: sem invencibilidade, sem stamina infinita, 1 dash padrão.
            if (SaveData.Instance != null)
            {
                SaveData.Instance.Assists.Invincible = false;
                SaveData.Instance.Assists.InfiniteStamina = false;
                SaveData.Instance.Assists.DashMode = Assists.DashModes.Normal;
            }

            if (_currentWaypointIndex < 0 || _currentWaypointIndex >= waypoints.Count)
            {
                Rectangle roomBox = level.Bounds;
                roomBox.Inflate(24, 24);
                int bestIdx = -1;
                float bestDist = float.MaxValue;
                for (int i = 0; i < waypoints.Count; i++)
                {
                    if (!roomBox.Contains((int)waypoints[i].X, (int)waypoints[i].Y))
                    {
                        continue;
                    }
                    float d = Vector2.DistanceSquared(player.Position, waypoints[i]);
                    if (d < bestDist)
                    {
                        bestDist = d;
                        bestIdx = i;
                    }
                }
                if (bestIdx < 0)
                {
                    bestDist = float.MaxValue;
                    for (int i = 0; i < waypoints.Count; i++)
                    {
                        float d = Vector2.DistanceSquared(player.Position, waypoints[i]);
                        if (d < bestDist)
                        {
                            bestDist = d;
                            bestIdx = i;
                        }
                    }
                    bestIdx = Math.Max(0, bestIdx);
                }
                _currentWaypointIndex = bestIdx;
            }

            // Avançar waypoints já alcançados ou superados dentro da sala atual
            while (_currentWaypointIndex < waypoints.Count - 1)
            {
                float curDist = Vector2.Distance(player.Position, waypoints[_currentWaypointIndex]);
                if (curDist <= 16f)
                {
                    _currentWaypointIndex++;
                    continue;
                }
                bool skippedAhead = false;
                int lookMax = Math.Min(waypoints.Count - 1, _currentWaypointIndex + 3);
                for (int j = _currentWaypointIndex + 1; j <= lookMax; j++)
                {
                    if (Vector2.Distance(player.Position, waypoints[j]) <= 18f)
                    {
                        _currentWaypointIndex = j + (j < waypoints.Count - 1 ? 1 : 0);
                        skippedAhead = true;
                        break;
                    }
                }
                if (!skippedAhead)
                {
                    break;
                }
            }

            Vector2 target = waypoints[_currentWaypointIndex];
            Vector2 delta = target - player.Position;
            float dt = Engine.DeltaTime;

            if (_dashCooldown > 0f) _dashCooldown -= dt;
            if (_jumpCooldown > 0f) _jumpCooldown -= dt;
            if (_holdJumpTimer > 0f) _holdJumpTimer -= dt;

            // 1. Direcional real (MoveX / MoveY) lido por NormalUpdate/ClimbUpdate
            int moveX = Math.Abs(delta.X) > 3f ? Math.Sign(delta.X) : 0;
            int moveY = Math.Abs(delta.Y) > 3f ? Math.Sign(delta.Y) : 0;

            bool onGround = player.OnGround(1);
            bool touchingLeftWall = player.CollideCheck<Solid>(player.Position + new Vector2(-3f, 0f));
            bool touchingRightWall = player.CollideCheck<Solid>(player.Position + new Vector2(3f, 0f));
            bool touchingWall = touchingLeftWall || touchingRightWall;
            bool inNormalState = player.StateMachine.State == Player.StNormal;
            bool inClimbState = player.StateMachine.State == Player.StClimb;

            // 2. Detecção de beira de abismo e espinhos à frente usando colisores reais da cena
            bool wantCrossWall = (touchingLeftWall && delta.X > 16f) || (touchingRightWall && delta.X < -16f);
            bool climbSameWall = touchingWall && !wantCrossWall && delta.Y < -6f && player.Stamina > 14f;
            _holdGrab = climbSameWall;
            if (climbSameWall && inClimbState)
            {
                moveX = 0;
                moveY = -1;
            }

            if (global::Celeste.Input.MoveX != null)
            {
                global::Celeste.Input.MoveX.Value = moveX;
            }
            if (global::Celeste.Input.MoveY != null)
            {
                global::Celeste.Input.MoveY.Value = moveY;
            }

            bool floorAhead = true;
            bool spikeAhead = false;
            if (onGround && moveX != 0)
            {
                floorAhead = player.CollideCheck<Solid>(player.Position + new Vector2(moveX * 10f, 3f));
                spikeAhead = level.CollideCheck<Spikes>(
                    new Rectangle((int)(player.Position.X + moveX * 10f - 4), (int)(player.Position.Y - 12f), 8, 14));
            }

            // 3. Pulo real com duração segurada (FilterButtonCheck mantém Jump.Check = true)
            bool ledgeJump = onGround && moveX != 0 && ((!floorAhead && delta.Y <= 8f) || spikeAhead);
            bool wallJumpNeeded = (touchingWall && wantCrossWall && delta.Y < 10f) ||
                                  (touchingWall && moveX != 0 && delta.Y <= 0f);
            bool climbHopUp = inClimbState && !wantCrossWall && delta.Y < -20f && Math.Abs(delta.X) < 18f && player.Stamina > 35f;
            bool verticalJumpNeeded = delta.Y < -8f;

            if (_jumpCooldown <= 0f &&
                ((inNormalState && onGround && (verticalJumpNeeded || wallJumpNeeded || ledgeJump)) ||
                 (inClimbState && (climbHopUp || wantCrossWall))))
            {
                player.Jump(true, true);
                _holdJumpTimer = delta.Y < -28f ? 0.24f : 0.18f;
                _jumpCooldown = 0.24f;
            }

            // 4. Dash único real no ápice/queda do pulo ou emergência (sem desperdiçar no arranque)
            bool nearApexOrFalling = player.Speed.Y >= -32f;
            bool needDash = (delta.Y < -44f && player.Speed.Y > -65f) ||
                            (nearApexOrFalling && (delta.Y < -14f || Math.Abs(delta.X) > 46f)) ||
                            (delta.Y < -6f && player.Speed.Y > 45f);
            if (inNormalState && !onGround && _dashCooldown <= 0f && player.CanDash && needDash)
            {
                Vector2 snappedDir = new Vector2(
                    Math.Abs(delta.X) > 6f ? Math.Sign(delta.X) : 0f,
                    Math.Abs(delta.Y) > 6f ? Math.Sign(delta.Y) : 0f
                );
                if (snappedDir == Vector2.Zero)
                {
                    snappedDir = new Vector2(moveX != 0 ? moveX : 1f, 0f);
                }
                snappedDir.Normalize();

                bool spikeInDash = level.CollideCheck<Spikes>(
                    new Rectangle((int)(player.Position.X + snappedDir.X * 18f - 4), (int)(player.Position.Y + snappedDir.Y * 18f - 10), 8, 12));
                if (!spikeInDash)
                {
                    player.OverrideDashDirection = snappedDir;
                    player.StateMachine.State = player.StartDash();
                    _dashCooldown = 0.35f;
                }
            }
        }

        public override void Render()
        {
            base.Render();

            Level level = Scene as Level;
            if (level == null || level.Session == null)
            {
                return;
            }

            int areaId = level.Session.Area.ID;
            string slug;
            if (!_areaToSlug.TryGetValue(areaId, out slug))
            {
                Draw.Rect(24f, 24f, 680f, 54f, new Color(11, 15, 25, 210));
                ActiveFont.DrawOutline(
                    "[StratGraph TAS] Entre em um Cap. do benchmark (1..7 ou 9) para ver a rota.",
                    new Vector2(40f, 38f),
                    Vector2.Zero,
                    new Vector2(0.45f, 0.45f),
                    Color.White,
                    2f,
                    Color.Black
                );
                return;
            }

            string rawRoom = level.Session.Level ?? "";
            string roomId = rawRoom.StartsWith("lvl_", StringComparison.OrdinalIgnoreCase)
                ? rawRoom
                : "lvl_" + rawRoom;

            string weaponRoom;
            if (_weaponRoomByChapter.TryGetValue(slug, out weaponRoom) &&
                string.Equals(roomId, weaponRoom, StringComparison.OrdinalIgnoreCase))
            {
                _armedLayerActive = true;
            }

            Color accent = _useBfsRoute
                ? new Color(255, 92, 119)
                : (_armedLayerActive ? new Color(0, 255, 136) : new Color(0, 229, 255));

            // 1. Desenhar linha de trajetória física TAS sobre a sala atual (câmera 320x180 -> HUD 1920x1080 = 6x)
            Dictionary<string, List<Vector2>> activeDict = _useBfsRoute
                ? _bfsWaypointsByChapter
                : _tasWaypointsByChapter;
            List<Vector2> wpts;
            if (activeDict.TryGetValue(slug, out wpts) && wpts.Count > 1)
            {
                Vector2 camPos = level.Camera.Position;
                for (int i = 0; i < wpts.Count - 1; i++)
                {
                    Vector2 s1 = (wpts[i] - camPos) * 6f;
                    Vector2 s2 = (wpts[i + 1] - camPos) * 6f;
                    if ((s1.X >= -100f && s1.X <= 2020f && s1.Y >= -100f && s1.Y <= 1180f) ||
                        (s2.X >= -100f && s2.X <= 2020f && s2.Y >= -100f && s2.Y <= 1180f))
                    {
                        Draw.Line(s1, s2, accent, 3f);
                    }
                }
            }

            string nextStep = "Seguir rota StratGraph";
            List<string> route;
            if (_stratRouteByChapter.TryGetValue(slug, out route) && route.Count > 0)
            {
                int pos = route.IndexOf(roomId);
                if (pos >= 0 && pos + 1 < route.Count)
                {
                    nextStep = route[pos + 1];
                }
                else if (pos == route.Count - 1)
                {
                    nextStep = "OBJETIVO ALCANÇADO (FIM)";
                }
                else
                {
                    nextStep = route[0] + " -> ... -> " + route[route.Count - 1];
                }
            }

            string contractedNote = "Nenhum beco contraído nesta sala";
            Dictionary<string, string> cMap;
            if (_contractedByChapter.TryGetValue(slug, out cMap))
            {
                string children;
                if (cMap.TryGetValue(roomId, out children) && !string.IsNullOrEmpty(children))
                {
                    contractedNote = "Coletar Beco(s) Contraído(s): " + children;
                }
            }

            string summary;
            if (!_summaryByChapter.TryGetValue(slug, out summary))
            {
                summary = "StratGraph (Dijkstra em Camadas L0->L1 + Contração)";
            }

            float boxX = 24f;
            float boxY = 24f;
            float boxW = 730f;
            float boxH = 142f;

            Draw.Rect(boxX, boxY, boxW, boxH, new Color(11, 15, 25, 215));
            Draw.Rect(boxX, boxY, 6f, boxH, accent);

            Vector2 scale = new Vector2(0.45f, 0.45f);
            ActiveFont.DrawOutline(
                "[StratGraph TAS] " + slug + " (" + roomId + ") | [F5] Bot: " +
                (_tasBotActive ? "ON" : "OFF") + " | [F6] Rota: " + (_useBfsRoute ? "BFS (L0)" : "StratGraph (L0->L1)"),
                new Vector2(boxX + 18f, boxY + 12f),
                Vector2.Zero,
                scale,
                Color.White,
                2f,
                Color.Black
            );

            string layerText = _armedLayerActive
                ? "Camada Atual: L1 (ARMADO / Dificuldade Reduzida em 80%)"
                : "Camada Atual: L0 (Desarmado -> Buscar Sala ARMA: " +
                  (_weaponRoomByChapter.ContainsKey(slug) ? _weaponRoomByChapter[slug] : "N/A") + ")";

            ActiveFont.DrawOutline(
                layerText,
                new Vector2(boxX + 18f, boxY + 42f),
                Vector2.Zero,
                scale,
                accent,
                2f,
                Color.Black
            );

            ActiveFont.DrawOutline(
                "Próximo Destino Ótimo: " + nextStep + " | " + contractedNote,
                new Vector2(boxX + 18f, boxY + 72f),
                Vector2.Zero,
                scale,
                new Color(255, 209, 102),
                2f,
                Color.Black
            );

            ActiveFont.DrawOutline(
                summary,
                new Vector2(boxX + 18f, boxY + 102f),
                Vector2.Zero,
                new Vector2(0.39f, 0.39f),
                new Color(180, 200, 235),
                2f,
                Color.Black
            );
        }
    }
}
