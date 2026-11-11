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

        private readonly Dictionary<string, string> _weaponRoomByChapter =
            new Dictionary<string, string>();

        private readonly Dictionary<string, Dictionary<string, string>> _contractedByChapter =
            new Dictionary<string, Dictionary<string, string>>();

        private readonly Dictionary<string, string> _summaryByChapter =
            new Dictionary<string, string>();

        private bool _armedLayerActive;
        private bool _tasBotActive;
        private int _currentWaypointIndex;
        private string _lastChapterSlug = "";

        public StratGraphHudEntity(string routesJsonPath)
        {
            Tag = Tags.HUD | Tags.Global | Tags.PauseUpdate | Tags.TransitionUpdate;
            Depth = -100000;
            LoadRoutesJson(routesJsonPath);
        }

        public static void AttachToLevel(Level level)
        {
            if (level == null)
            {
                return;
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
                int idx = raw.IndexOf(key, StringComparison.Ordinal);
                if (idx < 0)
                {
                    continue;
                }

                string block = raw.Substring(idx, Math.Min(28000, raw.Length - idx));

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
                    List<Vector2> pts = new List<Vector2>();
                    string[] pairs = wptsMatch.Groups[1].Value.Split(';');
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
                    _tasWaypointsByChapter[slug] = pts;
                }
            }
        }

        public override void Update()
        {
            base.Update();

            if (MInput.Keyboard != null && MInput.Keyboard.Pressed(Keys.F5))
            {
                _tasBotActive = !_tasBotActive;
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
                slug = "1_forsaken_city";
            }

            if (_lastChapterSlug != slug)
            {
                _lastChapterSlug = slug;
                _armedLayerActive = false;
                _currentWaypointIndex = 0;
            }

            if (!_tasBotActive)
            {
                return;
            }

            List<Vector2> waypoints;
            if (!_tasWaypointsByChapter.TryGetValue(slug, out waypoints) || waypoints.Count == 0)
            {
                return;
            }

            Player player = level.Tracker.GetEntity<Player>();
            if (player == null)
            {
                return;
            }

            if (_currentWaypointIndex >= waypoints.Count)
            {
                _currentWaypointIndex = 0;
            }

            Vector2 target = waypoints[_currentWaypointIndex];
            Vector2 delta = target - player.Position;
            float dist = delta.Length();

            float stepPx = 220f * Engine.DeltaTime;
            if (dist <= Math.Max(6f, stepPx))
            {
                player.Position = target;
                _currentWaypointIndex++;
            }
            else
            {
                delta.Normalize();
                player.Position += delta * stepPx;
            }
            player.Speed = Vector2.Zero;
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
                slug = "1_forsaken_city";
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

            Color accent = _armedLayerActive ? new Color(0, 255, 136) : new Color(0, 229, 255);

            // 1. Desenhar linha de trajetória física TAS sobre a sala atual (câmera 320x180 -> HUD 1920x1080 = 6x)
            List<Vector2> wpts;
            if (_tasWaypointsByChapter.TryGetValue(slug, out wpts) && wpts.Count > 1)
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
                "[StratGraph HUD + TAS] Cap.: " + slug + " | Sala: " + roomId +
                " | [F5] Bot TAS: " + (_tasBotActive ? "ATIVO" : "DESATIVADO"),
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
