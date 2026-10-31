using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;
using UnityEngine.Perception.Randomization.Samplers;
using UnityEngine.Rendering;

/// <summary>
/// Gives every robot with a JerseyRandomizerTag a team colour on its upper body. Each
/// iteration it bakes a recoloured copy of the robot's texture on the GPU (only inside the
/// tag's band, by default only the white parts) and swaps it into a per-robot material copy.
/// Play mode only: original materials and textures are never modified.
/// </summary>
[Serializable]
[AddRandomizerMenu("NomadZ/Jersey Randomizer")]
public class JerseyRandomizer : Randomizer
{
    [Serializable]
    public class JerseyColor
    {
        public string name;
        public Color color;
        public JerseyColor(string name, Color color) { this.name = name; this.color = color; }
    }

    public enum TeamMode
    {
        TwoTeams,    // per iteration: two different colours, robots split evenly between them
        Independent  // every robot draws its own colour
    }

    public TeamMode mode = TeamMode.TwoTeams;

    public List<JerseyColor> colors = new List<JerseyColor>
    {
        new JerseyColor("red", new Color(0.80f, 0.08f, 0.08f)),
        new JerseyColor("blue", new Color(0.08f, 0.20f, 0.75f)),
        new JerseyColor("yellow", new Color(0.95f, 0.80f, 0.10f)),
        new JerseyColor("black", new Color(0.04f, 0.04f, 0.04f)),
        new JerseyColor("white", new Color(0.92f, 0.92f, 0.92f)),
    };

    [Header("Variation per robot")]
    [Range(0f, 0.1f)] public float hueJitter = 0.02f;
    [Range(0f, 0.5f)] public float saturationJitter = 0.1f;
    [Range(0f, 0.5f)] public float valueJitter = 0.15f;
    [Range(0f, 1f)] public float minOpacity = 0.9f;
    [Range(0f, 1f)] public float maxOpacity = 1f;
    [Range(0f, 1f)] public float noJerseyProbability = 0f;

    [Header("What counts as 'white' (sRGB 0..1)")]
    [Range(0f, 1f)] public float whiteMaxSaturation = 0.25f;
    [Range(0f, 1f)] public float whiteMinBrightness = 0.45f;
    [Tooltip("Original brightness that gets the full jersey colour; darker texels get a darker shade.")]
    [Range(0.1f, 1f)] public float shadeReference = 0.85f;

    [Header("Band edges")]
    [Tooltip("Soft edge of the band, as a fraction of the band height.")]
    [Range(0f, 0.5f)] public float edgeSoftness = 0.08f;
    [Tooltip("Mask growth in texels, hides seams at UV island borders.")]
    [Range(0f, 4f)] public float dilatePixels = 1.5f;

    const string k_BakeShader = "Hidden/NomadZ/JerseyBake";   // Assets/NomadZ/Jersey/Resources/JerseyBake.shader

    class RobotState
    {
        public MeshFilter filter;
        public Renderer renderer;
        public Mesh mesh;
        public Material originalMaterial;
        public Material material;
        public Texture source;
        public RenderTexture mask;
        public RenderTexture output;
    }

    [NonSerialized] Material m_Bake;
    [NonSerialized] CommandBuffer m_Cmd;
    [NonSerialized] MaterialPropertyBlock m_Props;
    [NonSerialized] Dictionary<JerseyRandomizerTag, RobotState> m_Robots;
    [NonSerialized] List<JerseyRandomizerTag> m_Order;
    [NonSerialized] UniformSampler m_Random;

    static readonly int k_BandCenter = Shader.PropertyToID("_BandCenter");
    static readonly int k_BandSize = Shader.PropertyToID("_BandSize");
    static readonly int k_BandSoftness = Shader.PropertyToID("_BandSoftness");
    static readonly int k_MaskTex = Shader.PropertyToID("_MaskTex");
    static readonly int k_JerseyColor = Shader.PropertyToID("_JerseyColor");
    static readonly int k_Opacity = Shader.PropertyToID("_Opacity");
    static readonly int k_WhiteOnly = Shader.PropertyToID("_WhiteOnly");
    static readonly int k_WhiteSatMax = Shader.PropertyToID("_WhiteSatMax");
    static readonly int k_WhiteValMin = Shader.PropertyToID("_WhiteValMin");
    static readonly int k_ShadeRef = Shader.PropertyToID("_ShadeRef");
    static readonly int k_DilatePx = Shader.PropertyToID("_DilatePx");
    static readonly string[] k_TextureSlots = { "_BaseColorMap", "_MainTex", "_BaseMap" };

    protected override void OnScenarioStart()
    {
        m_Robots = new Dictionary<JerseyRandomizerTag, RobotState>();
        m_Order = new List<JerseyRandomizerTag>();
        m_Props = new MaterialPropertyBlock();
        m_Cmd = new CommandBuffer { name = "Jersey bake" };
        m_Random = new UniformSampler(0f, 1f);

        var shader = Shader.Find(k_BakeShader);
        if (shader == null)
            Debug.LogError($"JerseyRandomizer: shader {k_BakeShader} not found, jerseys disabled.");
        else
            m_Bake = new Material(shader);
    }

    protected override void OnIterationStart()
    {
        if (m_Bake == null || colors.Count == 0)
            return;

        m_Order.Clear();
        foreach (var tag in tagManager.Query<JerseyRandomizerTag>())
            m_Order.Add(tag);

        // Fisher-Yates shuffle so team membership changes every iteration.
        for (int i = m_Order.Count - 1; i > 0; i--)
        {
            int j = Mathf.Min((int)(Rand() * (i + 1)), i);
            (m_Order[i], m_Order[j]) = (m_Order[j], m_Order[i]);
        }

        int teamA = PickColor(-1);
        int teamB = colors.Count > 1 ? PickColor(teamA) : teamA;

        for (int i = 0; i < m_Order.Count; i++)
        {
            var tag = m_Order[i];
            var robot = GetOrCreate(tag);
            if (robot == null)
                continue;

            if (Rand() < noJerseyProbability || !tag.TryGetBand(out _, out var center, out var size, out var axis))
            {
                robot.renderer.sharedMaterial = robot.originalMaterial;
                continue;
            }

            int colorIndex = mode == TeamMode.TwoTeams ? (i % 2 == 0 ? teamA : teamB) : PickColor(-1);
            Bake(robot, tag, center, size, size[axis], Jitter(colors[colorIndex].color));
            robot.renderer.sharedMaterial = robot.material;
        }
    }

    protected override void OnScenarioComplete()
    {
        if (m_Robots != null)
        {
            foreach (var robot in m_Robots.Values)
            {
                if (robot == null)
                    continue;
                if (robot.renderer != null)
                    robot.renderer.sharedMaterial = robot.originalMaterial;
                UnityEngine.Object.Destroy(robot.material);
                robot.mask?.Release();
                robot.output?.Release();
            }
            m_Robots.Clear();
        }
        m_Cmd?.Release();
        if (m_Bake != null)
            UnityEngine.Object.Destroy(m_Bake);
    }

    void Bake(RobotState robot, JerseyRandomizerTag tag, Vector3 center, Vector3 size, float bandHeight, Color color)
    {
        // Pass 0: band mask in texture space (recomputed each time so the band can be tuned in Play mode).
        m_Props.Clear();
        m_Props.SetVector(k_BandCenter, center);
        m_Props.SetVector(k_BandSize, size);
        m_Props.SetFloat(k_BandSoftness, Mathf.Max(bandHeight * edgeSoftness, 1e-6f));

        m_Cmd.Clear();
        m_Cmd.SetRenderTarget(robot.mask);
        m_Cmd.ClearRenderTarget(false, true, Color.black);
        for (int s = 0; s < robot.mesh.subMeshCount; s++)
            m_Cmd.DrawMesh(robot.mesh, Matrix4x4.identity, m_Bake, s, 0, m_Props);
        Graphics.ExecuteCommandBuffer(m_Cmd);

        // Pass 1: recoloured copy of the original texture.
        m_Bake.SetTexture(k_MaskTex, robot.mask);
        m_Bake.SetColor(k_JerseyColor, color.linear);
        m_Bake.SetFloat(k_Opacity, Mathf.Lerp(minOpacity, maxOpacity, Rand()));
        m_Bake.SetFloat(k_WhiteOnly, tag.whitePartsOnly ? 1f : 0f);
        m_Bake.SetFloat(k_WhiteSatMax, whiteMaxSaturation);
        m_Bake.SetFloat(k_WhiteValMin, whiteMinBrightness);
        m_Bake.SetFloat(k_ShadeRef, shadeReference);
        m_Bake.SetFloat(k_DilatePx, dilatePixels);
        Graphics.Blit(robot.source, robot.output, m_Bake, 1);
    }

    RobotState GetOrCreate(JerseyRandomizerTag tag)
    {
        if (!m_Robots.TryGetValue(tag, out var robot))
        {
            var filter = tag.MeshFilter;
            var renderer = filter != null ? filter.GetComponent<Renderer>() : null;
            robot = renderer != null ? new RobotState { filter = filter, renderer = renderer } : null;
            if (robot == null)
                Debug.LogWarning($"JerseyRandomizer: {tag.name} has no mesh renderer, skipped.");
            m_Robots[tag] = robot;
        }
        return robot != null && Sync(robot, tag.name) ? robot : null;
    }

    /// <summary>
    /// Follows mesh/material changes made by other randomizers (e.g. pose swaps) and makes sure
    /// the robot has a material copy whose base texture is its jersey render texture.
    /// </summary>
    bool Sync(RobotState robot, string robotName)
    {
        robot.mesh = robot.filter.sharedMesh;
        var current = robot.renderer.sharedMaterial;
        if (current != null && (current == robot.material || current == robot.originalMaterial))
            return robot.mesh != null;

        Texture source = null;
        string slot = null;
        if (current != null)
        {
            foreach (var name in k_TextureSlots)
            {
                if (current.HasProperty(name) && current.GetTexture(name) != null)
                {
                    source = current.GetTexture(name);
                    slot = name;
                    break;
                }
            }
        }
        if (robot.mesh == null || source == null)
        {
            Debug.LogWarning($"JerseyRandomizer: {robotName} has no mesh or no base texture, skipped.");
            return false;
        }

        if (robot.output == null || robot.output.width != source.width || robot.output.height != source.height)
        {
            robot.output?.Release();
            robot.mask?.Release();

            robot.output = new RenderTexture(source.width, source.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
            {
                useMipMap = true,
                autoGenerateMips = true,
                filterMode = FilterMode.Trilinear,
                anisoLevel = 4,
                name = $"{robotName} jersey"
            };
            robot.output.Create();

            robot.mask = new RenderTexture(source.width, source.height, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear)
            {
                name = $"{robotName} jersey mask"
            };
            robot.mask.Create();
        }
        robot.output.wrapMode = source.wrapMode;

        if (robot.material != null)
            UnityEngine.Object.Destroy(robot.material);
        robot.originalMaterial = current;
        robot.source = source;
        robot.material = new Material(current) { name = $"{current.name} (jersey)" };
        robot.material.SetTexture(slot, robot.output);
        return true;
    }

    int PickColor(int exclude)
    {
        int n = exclude >= 0 ? colors.Count - 1 : colors.Count;
        int k = Mathf.Min((int)(Rand() * n), n - 1);
        return exclude >= 0 && k >= exclude ? k + 1 : k;
    }

    Color Jitter(Color c)
    {
        Color.RGBToHSV(c, out var h, out var s, out var v);
        h = Mathf.Repeat(h + (Rand() * 2f - 1f) * hueJitter, 1f);
        s = Mathf.Clamp01(s * (1f + (Rand() * 2f - 1f) * saturationJitter));
        v = Mathf.Clamp01(v * (1f + (Rand() * 2f - 1f) * valueJitter));
        return Color.HSVToRGB(h, s, v);
    }

    float Rand() => m_Random.Sample();
}
